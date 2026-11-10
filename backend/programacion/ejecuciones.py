from uuid import uuid4
from datetime import timedelta
from django.db.models import Q

from django.db import transaction
from django.utils import timezone

from disponibilidad.models import Auditoria

from .generador import generar_horario, hay_cruce
from .models import Asignacion, ConjuntoInsumos, EjecucionGeneracion, Propuesta


LIMITE_MS = 5_000
MAX_INTENTOS = 10_000


def guardar_selecciones(version, conjunto, asignaciones):
    ocupadas = []

    for oferta_id, plan in asignaciones.items():
        oferta = conjunto.ofertas.select_related(
            "curso_propuesto__revision__declaracion__convocado",
        ).get(pk=oferta_id)

        if not plan:
            raise ValueError("Una oferta seleccionada debe tener todas sus sesiones.")

        habilitada = oferta.opciones_habilitadas.get(pk=plan[0].opcion_habilitada_id)
        correspondencias = {
            (registro.sesion_id, registro.bloque_id): registro.pk
            for registro in habilitada.correspondencias.all()
        }
        sesiones_esperadas = set(
            oferta.sesiones_requeridas.values_list("pk", flat=True)
        )

        if len(plan) != len(sesiones_esperadas) or {
            item.sesion.pk for item in plan
        } != sesiones_esperadas:
            raise ValueError(f"La oferta {oferta.codigo} tiene sesiones incompletas o repetidas.")

        docente_id = oferta.curso_propuesto.revision.declaracion.convocado.docente_id
        filas = []

        for item in plan:
            bloque = item.bloque
            franja = item.franja
            correspondencia_id = correspondencias.get((item.sesion.pk, bloque.pk))
            if (
                item.opcion_habilitada_id != habilitada.pk
                or correspondencia_id is None
                or item.docente_id != docente_id
                or item.grupo_id != oferta.grupo_id
                or franja.conjunto_id != conjunto.pk
                or franja.dia != bloque.dia
                or franja.inicio > bloque.inicio
                or franja.fin < bloque.fin
            ):
                raise ValueError(f"La oferta {oferta.codigo} tiene una asignación inválida.")

            if any(hay_cruce(item, anterior) for anterior in ocupadas):
                raise ValueError("La propuesta contiene un cruce de docente, grupo o salón.")

            ocupadas.append(item)
            filas.append((correspondencia_id, franja.pk))

        seleccion = version.selecciones.create(
            oferta=oferta,
            opcion_habilitada=habilitada,
        )
        Asignacion.objects.bulk_create([
            Asignacion(seleccion=seleccion, correspondencia_id=correspondencia, franja_id=franja)
            for correspondencia, franja in filas
        ])


@transaction.atomic
def guardar_resultado(ejecucion_id, token, resultado):
    ejecucion = EjecucionGeneracion.objects.select_for_update().get(pk=ejecucion_id)
    if (
        ejecucion.estado != EjecucionGeneracion.Estado.EJECUTANDO
        or ejecucion.token_ejecucion != token
    ):
        raise ValueError("Esta ejecución ya no puede guardar resultados.")

    conjunto = ejecucion.conjunto
    asignaciones = resultado["asignaciones"]
    resultado_ejecucion = EjecucionGeneracion.Resultado.SIN_RESULTADO

    if asignaciones:
        completa = len(asignaciones) == conjunto.ofertas.count()
        propuesta = Propuesta.objects.create(ejecucion=ejecucion)
        version = propuesta.versiones.create(
            numero=1,
            estado="COMPLETA" if completa else "PARCIAL",
            creado_por_id=ejecucion.solicitado_por_id,
        )
        guardar_selecciones(version, conjunto, asignaciones)
        propuesta.version_trabajo = version
        propuesta.save(update_fields=["version_trabajo"])
        resultado_ejecucion = (
            EjecucionGeneracion.Resultado.COMPLETO
            if completa else EjecucionGeneracion.Resultado.PARCIAL
        )

    ejecucion.estado = EjecucionGeneracion.Estado.FINALIZADA
    ejecucion.resultado = resultado_ejecucion
    ejecucion.condicion_termino = (
        "LIMITE_ALCANZADO" if resultado["limite_alcanzado"] else "BUSQUEDA_TERMINADA"
    )
    ejecucion.fin_en = timezone.now()
    ejecucion.parametros = {
        **ejecucion.parametros,
        "intentos": resultado["intentos"],
        "pendientes": resultado["pendientes"],
    }
    ejecucion.save(update_fields=[
        "estado", "resultado", "condicion_termino", "fin_en", "parametros",
    ])

    Auditoria.objects.create(
        usuario_id=ejecucion.solicitado_por_id,
        operacion="FINALIZAR_GENERACION",
        periodo_id=conjunto.recopilacion.periodo_id,
        objeto_tipo="ejecucion_generacion",
        objeto_id=ejecucion.pk,
        detalle={"resultado": resultado_ejecucion, "conjunto_id": conjunto.pk},
    )

    return ejecucion


def encolar_generacion(conjunto, usuario, clave_solicitud):
    if conjunto.estado != ConjuntoInsumos.Estado.CONGELADO:
        raise ValueError("Congela el conjunto antes de generar el horario.")

    ejecucion, creada = EjecucionGeneracion.objects.get_or_create(
        clave_solicitud=clave_solicitud,
        defaults={
            "conjunto": conjunto,
            "solicitado_por": usuario,
            "estado": EjecucionGeneracion.Estado.EN_COLA,
            "limite_ms": LIMITE_MS,
            "parametros": {"max_intentos": MAX_INTENTOS},
        },
    )

    if not creada and (
        ejecucion.conjunto_id != conjunto.pk
        or ejecucion.solicitado_por_id != usuario.pk
    ):
        raise ValueError("La clave de solicitud ya pertenece a otra ejecución.")

    return ejecucion


@transaction.atomic
def tomar_ejecucion(ejecucion_id=None):
    ahora = timezone.now()
    vencimiento = ahora - timedelta(minutes=2)

    pendientes = EjecucionGeneracion.objects.select_for_update(skip_locked=True).filter(
        Q(estado=EjecucionGeneracion.Estado.EN_COLA)
        | Q(
            estado=EjecucionGeneracion.Estado.EJECUTANDO,
            pulso_en__lt=vencimiento,
        )
    )

    if ejecucion_id is not None:
        pendientes = pendientes.filter(pk=ejecucion_id)

    ejecucion = pendientes.order_by("pk").first()
    if ejecucion is None:
        return None

    ejecucion.estado = EjecucionGeneracion.Estado.EJECUTANDO
    ejecucion.inicio_en = ahora
    ejecucion.pulso_en = ahora
    ejecucion.token_ejecucion = uuid4()
    ejecucion.save(update_fields=[
        "estado", "inicio_en", "pulso_en", "token_ejecucion",
    ])
    return ejecucion


def procesar_ejecucion(ejecucion):
    token = ejecucion.token_ejecucion
    try:
        resultado = generar_horario(
            ejecucion.conjunto,
            max_intentos=ejecucion.parametros["max_intentos"],
            limite_ms=ejecucion.limite_ms,
        )
        return guardar_resultado(ejecucion.pk, token, resultado)
    except Exception:
        EjecucionGeneracion.objects.filter(
            pk=ejecucion.pk,
            estado=EjecucionGeneracion.Estado.EJECUTANDO,
            token_ejecucion=token,
        ).update(
            estado=EjecucionGeneracion.Estado.FALLIDA,
            condicion_termino="ERROR",
            fin_en=timezone.now(),
        )
        raise


def ejecutar_generacion(conjunto, usuario, clave_solicitud):
    ejecucion = encolar_generacion(conjunto, usuario, clave_solicitud)
    tomada = tomar_ejecucion(ejecucion.pk)
    if tomada is None:
        ejecucion.refresh_from_db()
        return ejecucion

    return procesar_ejecucion(tomada)