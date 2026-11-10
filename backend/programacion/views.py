import json
from uuid import UUID

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import date, datetime, timedelta
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_GET
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .ajustes import AjusteHorarioError, cambiar_salon
from .ejecuciones import encolar_generacion

from disponibilidad.models import Auditoria, Recopilacion, RevisionFicha, CursoPropuesto

from .models import ConjuntoInsumos, InsumoRevision, Grupo, Oferta, SesionRequerida, CorrespondenciaSesion,Salon, EjecucionGeneracion, Asignacion, Propuesta, VersionHorario


@require_POST
@transaction.atomic
def crear_conjunto_insumos(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.add_conjuntoinsumos"):
        return JsonResponse({"error": "No tienes permiso para preparar insumos."}, status=403)

    recopilacion = Recopilacion.objects.select_for_update().filter(
        pk=recopilacion_id,
    ).first()
    if recopilacion is None:
        return JsonResponse({"error": "Recopilación no encontrada."}, status=404)

    if recopilacion.estado != Recopilacion.Estado.CERRADA:
        return JsonResponse(
            {"error": "Cierra la recopilación antes de preparar los insumos."},
            status=409,
        )

    revisiones_ids = list(
        RevisionFicha.objects.filter(
            declaracion__convocado__recopilacion=recopilacion,
            declaracion__convocado__activo=True,
            estado=RevisionFicha.Estado.ENVIADA,
            enviada_en__isnull=False,
        )
        .order_by("declaracion_id", "-numero")
        .distinct("declaracion_id")
        .values_list("pk", flat=True)
    )
    if not revisiones_ids:
        return JsonResponse({"error": "No hay fichas enviadas para programar."}, status=409)

    ultimo = recopilacion.conjuntos_insumos.order_by("-numero").first()
    mismo_borrador = (
        ultimo is not None
        and ultimo.estado == ConjuntoInsumos.Estado.BORRADOR
        and set(ultimo.insumos_revision.values_list("revision_id", flat=True))
        == set(revisiones_ids)
    )

    if mismo_borrador:
        conjunto = ultimo
        codigo_http = 200
    else:
        conjunto = recopilacion.conjuntos_insumos.create(
            numero=ultimo.numero + 1 if ultimo else 1,
            creado_por=request.user,
        )
        InsumoRevision.objects.bulk_create([
            InsumoRevision(conjunto=conjunto, revision_id=revision_id)
            for revision_id in revisiones_ids
        ])
        Auditoria.objects.create(
            usuario=request.user,
            operacion="CREAR_CONJUNTO_INSUMOS",
            periodo_id=recopilacion.periodo_id,
            objeto_tipo="conjunto_insumos",
            objeto_id=conjunto.pk,
            detalle={"recopilacion_id": recopilacion.pk, "numero": conjunto.numero},
        )
        codigo_http = 201

    return JsonResponse({
        "conjunto": {
            "id": conjunto.pk,
            "numero": conjunto.numero,
            "estado": conjunto.estado,
            "total_revisiones": len(revisiones_ids),
        },
    }, status=codigo_http)

@require_POST
@transaction.atomic
def crear_oferta(request, conjunto_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.add_oferta"):
        return JsonResponse({"error": "No tienes permiso para registrar ofertas."}, status=403)

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(datos, dict):
        return JsonResponse({"error": "Envía los datos de la oferta."}, status=400)

    codigo = datos.get("codigo")
    curso_id = datos.get("curso_propuesto_id")
    grupo_id = datos.get("grupo_id")
    duraciones = datos.get("duraciones_min")

    if not isinstance(codigo, str) or not 1 <= len(codigo.strip()) <= 30:
        return JsonResponse({"error": "El código debe tener entre 1 y 30 caracteres."}, status=400)
    codigo = codigo.strip()

    if type(curso_id) is not int or curso_id < 1 or type(grupo_id) is not int or grupo_id < 1:
        return JsonResponse({"error": "Selecciona un curso y un grupo válidos."}, status=400)

    if not isinstance(duraciones, list) or not duraciones or any(
        type(minutos) is not int or not 1 <= minutos <= 2_147_483_647
        for minutos in duraciones
    ):
        return JsonResponse(
            {"error": "Indica al menos una sesión con duración en minutos enteros positivos."},
            status=400,
        )

    conjunto = ConjuntoInsumos.objects.select_for_update().filter(pk=conjunto_id).first()
    if conjunto is None:
        return JsonResponse({"error": "Conjunto no encontrado."}, status=404)
    if conjunto.estado != ConjuntoInsumos.Estado.BORRADOR:
        return JsonResponse({"error": "El conjunto ya está congelado."}, status=409)

    curso = CursoPropuesto.objects.filter(
        pk=curso_id,
        revision__estado=RevisionFicha.Estado.ENVIADA,
        revision__insumos_programacion__conjunto=conjunto,
        revision__declaracion__convocado__recopilacion_id=conjunto.recopilacion_id,
    ).first()
    if curso is None:
        return JsonResponse({"error": "El curso no pertenece a las fichas del conjunto."}, status=400)

    grupo = Grupo.objects.filter(
        pk=grupo_id, periodo_id=conjunto.recopilacion.periodo_id, activo=True,
    ).first()
    if grupo is None:
        return JsonResponse({"error": "El grupo debe estar activo y pertenecer al mismo periodo."}, status=400)

    if conjunto.ofertas.filter(codigo=codigo).exists():
        return JsonResponse({"error": "Ese código de oferta ya está en uso."}, status=409)
    if conjunto.ofertas.filter(curso_propuesto=curso, grupo=grupo).exists():
        return JsonResponse({"error": "El curso ya tiene una oferta para ese grupo."}, status=409)

    oferta = conjunto.ofertas.create(
        codigo=codigo,
        curso_propuesto=curso,
        grupo=grupo,
        codigo_grupo_copia=grupo.codigo,
        grupo_copia=grupo.denominacion,
    )
    SesionRequerida.objects.bulk_create([
        SesionRequerida(oferta=oferta, numero=numero, duracion_min=minutos)
        for numero, minutos in enumerate(duraciones, start=1)
    ])

    return JsonResponse({
        "oferta": {
            "id": oferta.pk,
            "codigo": oferta.codigo,
            "curso": curso.denominacion_copia,
            "grupo": oferta.grupo_copia,
            "duraciones_min": duraciones,
        },
    }, status=201)
def duracion_bloque(bloque):
    return (
        datetime.combine(date.min, bloque.fin)
        - datetime.combine(date.min, bloque.inicio)
    )

def emparejar_sesiones(sesiones, bloques):
    sesiones_ordenadas = sorted(
        sesiones, key=lambda sesion: (sesion.duracion_min, sesion.numero),
    )
    bloques_ordenados = sorted(
        bloques, key=lambda bloque: (
            duracion_bloque(bloque), bloque.dia, bloque.inicio, bloque.numero,
        ),
    )

    if len(sesiones_ordenadas) != len(bloques_ordenados):
        return None, "La cantidad de bloques no coincide con las sesiones requeridas."

    pares = list(zip(sesiones_ordenadas, bloques_ordenados))
    if any(
        timedelta(minutes=sesion.duracion_min) != duracion_bloque(bloque)
        for sesion, bloque in pares
    ):
        return None, "Las duraciones de los bloques no coinciden con las sesiones requeridas."

    return sorted(pares, key=lambda par: par[0].numero), None


@require_GET
def evaluar_opciones_oferta(request, oferta_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.view_oferta"):
        return JsonResponse({"error": "No tienes permiso para consultar ofertas."}, status=403)

    oferta = Oferta.objects.select_related("curso_propuesto").filter(
        pk=oferta_id,
    ).first()
    if oferta is None:
        return JsonResponse({"error": "Oferta no encontrada."}, status=404)

    sesiones = list(oferta.sesiones_requeridas.order_by("duracion_min", "numero"))
    if not sesiones:
        return JsonResponse({"error": "La oferta no tiene sesiones requeridas."}, status=409)

    duraciones_requeridas = [timedelta(minutes=sesion.duracion_min) for sesion in sesiones]

    opciones = oferta.curso_propuesto.opciones.order_by("numero").prefetch_related("bloques")
    evaluaciones = []

    for opcion in opciones:
        pares, motivo = emparejar_sesiones(sesiones, opcion.bloques.all())
        evaluaciones.append({
            "id": opcion.pk,
            "numero": opcion.numero,
            "compatible": pares is not None,
            "motivo": motivo,
            "correspondencias": [
                {
                    "sesion": sesion.numero,
                    "bloque_id": bloque.pk,
                    "dia": bloque.dia,
                    "inicio": bloque.inicio.strftime("%H:%M"),
                    "fin": bloque.fin.strftime("%H:%M"),
                }
                for sesion, bloque in (pares or [])
            ],
        })

    return JsonResponse({"oferta_id": oferta.pk, "opciones": evaluaciones})
@require_POST
@transaction.atomic
def habilitar_opcion(request, oferta_id, opcion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.add_opcionhabilitada"):
        return JsonResponse({"error": "No tienes permiso para habilitar opciones."}, status=403)

    oferta = (
        Oferta.objects.select_related("conjunto", "curso_propuesto")
        .select_for_update(of=("conjunto",))
        .filter(pk=oferta_id)
        .first()
    )
    if oferta is None:
        return JsonResponse({"error": "Oferta no encontrada."}, status=404)

    if oferta.conjunto.estado != ConjuntoInsumos.Estado.BORRADOR:
        return JsonResponse({"error": "El conjunto ya está congelado."}, status=409)

    opcion = oferta.curso_propuesto.opciones.filter(pk=opcion_id).first()
    if opcion is None:
        return JsonResponse({"error": "La opción no pertenece al curso de esta oferta."}, status=404)

    sesiones = list(oferta.sesiones_requeridas.all())
    if not sesiones:
        return JsonResponse({"error": "La oferta no tiene sesiones requeridas."}, status=409)

    pares, motivo = emparejar_sesiones(sesiones, opcion.bloques.all())
    if pares is None:
        return JsonResponse({"error": motivo}, status=400)

    habilitada, creada = oferta.opciones_habilitadas.get_or_create(
        opcion_semanal=opcion,
    )
    if creada:
        CorrespondenciaSesion.objects.bulk_create([
            CorrespondenciaSesion(opcion_habilitada=habilitada, sesion=sesion, bloque=bloque)
            for sesion, bloque in pares
        ])

    return JsonResponse({
        "id": habilitada.pk,
        "oferta_id": oferta.pk,
        "opcion_id": opcion.pk,
        "total_sesiones": habilitada.correspondencias.count(),
    }, status=201 if creada else 200)

@require_POST
@transaction.atomic
def registrar_franja(request, conjunto_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.add_franjautilizable"):
        return JsonResponse({"error": "No tienes permiso para registrar franjas."}, status=403)

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(datos, dict):
        return JsonResponse({"error": "Indica el salón, el día y las horas."}, status=400)

    salon_id = datos.get("salon_id")
    dia = datos.get("dia")
    if type(salon_id) is not int or not 1 <= salon_id <= 2**63 - 1:
        return JsonResponse({"error": "Selecciona un salón válido."}, status=400)
    if type(dia) is not int or not 1 <= dia <= 6:
        return JsonResponse({"error": "Selecciona un día de lunes a sábado."}, status=400)

    try:
        inicio = datetime.strptime(datos.get("inicio"), "%H:%M").time()
        fin = datetime.strptime(datos.get("fin"), "%H:%M").time()
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ingresa las horas en formato HH:MM."}, status=400)

    if inicio >= fin:
        return JsonResponse({"error": "La hora de fin debe ser posterior a la de inicio."}, status=400)

    conjunto = ConjuntoInsumos.objects.select_for_update().filter(pk=conjunto_id).first()
    if conjunto is None:
        return JsonResponse({"error": "Conjunto no encontrado."}, status=404)
    if conjunto.estado != ConjuntoInsumos.Estado.BORRADOR:
        return JsonResponse({"error": "El conjunto ya está congelado."}, status=409)

    salon = Salon.objects.filter(pk=salon_id, activo=True).first()
    if salon is None:
        return JsonResponse({"error": "El salón no está disponible en el catálogo."}, status=404)

    franja, creada = conjunto.franjas_utilizables.get_or_create(
        salon=salon,
        dia=dia,
        inicio=inicio,
        fin=fin,
        defaults={"codigo_salon_copia": salon.codigo},
    )

    return JsonResponse({
        "id": franja.pk,
        "salon": franja.codigo_salon_copia,
        "dia": franja.dia,
        "inicio": franja.inicio.strftime("%H:%M"),
        "fin": franja.fin.strftime("%H:%M"),
    }, status=201 if creada else 200)

def validar_conjunto(conjunto):
    insumos = list(conjunto.insumos_revision.select_related(
        "revision__declaracion__convocado",
    ))
    if not insumos:
        raise ValueError("El conjunto no tiene fichas enviadas.")

    revisiones_ids = set()
    docentes_ids = set()

    for insumo in insumos:
        revision = insumo.revision
        convocado = revision.declaracion.convocado
        if (
            revision.estado != RevisionFicha.Estado.ENVIADA
            or revision.enviada_en is None
            or convocado.recopilacion_id != conjunto.recopilacion_id
            or convocado.docente_id in docentes_ids
        ):
            raise ValueError("Las fichas del conjunto tienen referencias inconsistentes.")

        revisiones_ids.add(revision.pk)
        docentes_ids.add(convocado.docente_id)

    ofertas = list(
        conjunto.ofertas.select_related("curso_propuesto", "grupo")
        .prefetch_related(
            "sesiones_requeridas",
            "opciones_habilitadas__opcion_semanal__bloques",
            "opciones_habilitadas__correspondencias__sesion",
            "opciones_habilitadas__correspondencias__bloque",
        )
        .order_by("codigo")
    )
    if not ofertas:
        raise ValueError("Agrega al menos una oferta antes de congelar el conjunto.")

    periodo_id = conjunto.recopilacion.periodo_id
    franjas = list(conjunto.franjas_utilizables.all())
    advertencias = []

    for oferta in ofertas:
        if (
            oferta.curso_propuesto.revision_id not in revisiones_ids
            or oferta.grupo.periodo_id != periodo_id
        ):
            raise ValueError(f"La oferta {oferta.codigo} tiene un curso o grupo inválido.")

        sesiones_ids = {sesion.pk for sesion in oferta.sesiones_requeridas.all()}
        if not sesiones_ids:
            raise ValueError(f"La oferta {oferta.codigo} no tiene sesiones requeridas.")

        habilitadas = list(oferta.opciones_habilitadas.all())
        if not habilitadas:
            advertencias.append({
                "oferta": oferta.codigo,
                "motivo": "No tiene opciones habilitadas.",
            })
            continue

        tiene_salon_para_todos_los_bloques = False

        for habilitada in habilitadas:
            opcion = habilitada.opcion_semanal
            correspondencias = list(habilitada.correspondencias.all())
            bloques_ids = {bloque.pk for bloque in opcion.bloques.all()}

            if (
                opcion.curso_propuesto_id != oferta.curso_propuesto_id
                or len(correspondencias) != len(sesiones_ids)
                or {registro.sesion_id for registro in correspondencias} != sesiones_ids
                or {registro.bloque_id for registro in correspondencias} != bloques_ids
                or any(
                    duracion_bloque(registro.bloque)
                    != timedelta(minutes=registro.sesion.duracion_min)
                    for registro in correspondencias
                )
            ):
                raise ValueError(
                    f"La opción {opcion.numero} de {oferta.codigo} "
                    "no cubre correctamente las sesiones requeridas."
                )

            if all(
                any(
                    franja.dia == registro.bloque.dia
                    and franja.inicio <= registro.bloque.inicio
                    and franja.fin >= registro.bloque.fin
                    for franja in franjas
                )
                for registro in correspondencias
            ):
                tiene_salon_para_todos_los_bloques = True

        if not tiene_salon_para_todos_los_bloques:
            advertencias.append({
                "oferta": oferta.codigo,
                "motivo": "Ninguna opción tiene salón disponible para todos sus bloques.",
            })

    return advertencias


@require_POST
@transaction.atomic
def congelar_conjunto(request, conjunto_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.change_conjuntoinsumos"):
        return JsonResponse({"error": "No tienes permiso para congelar el conjunto."}, status=403)

    conjunto = (
        ConjuntoInsumos.objects.select_related("recopilacion")
        .select_for_update(of=("self", "recopilacion"))
        .filter(pk=conjunto_id)
        .first()
    )
    if conjunto is None:
        return JsonResponse({"error": "Conjunto no encontrado."}, status=404)

    ya_congelado = conjunto.estado == ConjuntoInsumos.Estado.CONGELADO
    if not ya_congelado and conjunto.recopilacion.estado != Recopilacion.Estado.CERRADA:
        return JsonResponse({"error": "Cierra la recopilación antes de congelar."}, status=409)

    try:
        advertencias = validar_conjunto(conjunto)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    if not ya_congelado:
        conjunto.estado = ConjuntoInsumos.Estado.CONGELADO
        conjunto.congelado_en = timezone.now()
        conjunto.save(update_fields=["estado", "congelado_en"])

        Auditoria.objects.create(
            usuario=request.user,
            operacion="CONGELAR_CONJUNTO_INSUMOS",
            periodo_id=conjunto.recopilacion.periodo_id,
            objeto_tipo="conjunto_insumos",
            objeto_id=conjunto.pk,
            detalle={"advertencias": advertencias},
        )

    return JsonResponse({
        "id": conjunto.pk,
        "estado": conjunto.estado,
        "congelado_en": conjunto.congelado_en,
        "advertencias": advertencias,
    })

def datos_ejecucion(ejecucion):
    propuesta = getattr(ejecucion, "propuesta", None)

    return {
        "id": ejecucion.pk,
        "conjunto_id": ejecucion.conjunto_id,
        "estado": ejecucion.estado,
        "resultado": ejecucion.resultado,
        "condicion_termino": ejecucion.condicion_termino,
        "propuesta_id": propuesta.pk if propuesta is not None else None,
        "pendientes": ejecucion.parametros.get("pendientes", []),
    }


@require_POST
def solicitar_generacion(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.add_ejecuciongeneracion"):
        return JsonResponse({"error": "No tienes permiso para generar horarios."}, status=403)

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(datos, dict):
        return JsonResponse({"error": "Indica el conjunto y la clave de solicitud."}, status=400)

    conjunto_id = datos.get("conjunto_id")
    clave = datos.get("clave_solicitud")

    if type(conjunto_id) is not int or not 1 <= conjunto_id <= 2**63 - 1:
        return JsonResponse({"error": "Indica un conjunto válido."}, status=400)

    if not isinstance(clave, str):
        return JsonResponse({"error": "Indica una clave de solicitud válida."}, status=400)

    try:
        clave_solicitud = UUID(clave)
    except ValueError:
        return JsonResponse({"error": "La clave de solicitud debe ser un UUID."}, status=400)

    conjunto = ConjuntoInsumos.objects.filter(pk=conjunto_id).first()
    if conjunto is None:
        return JsonResponse({"error": "Conjunto no encontrado."}, status=404)

    try:
        ejecucion = encolar_generacion(conjunto, request.user, clave_solicitud)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=409)

    en_proceso = ejecucion.estado in (
        EjecucionGeneracion.Estado.EN_COLA,
        EjecucionGeneracion.Estado.EJECUTANDO,
    )
    return JsonResponse(datos_ejecucion(ejecucion), status=202 if en_proceso else 200)


@require_GET
def consultar_ejecucion(request, ejecucion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.view_ejecuciongeneracion"):
        return JsonResponse({"error": "No tienes permiso para consultar la ejecución."}, status=403)

    ejecucion = EjecucionGeneracion.objects.select_related("propuesta").filter(
        pk=ejecucion_id,
    ).first()
    if ejecucion is None:
        return JsonResponse({"error": "Ejecución no encontrada."}, status=404)

    return JsonResponse(datos_ejecucion(ejecucion))

@never_cache
@require_GET
def consultar_propuesta(request, propuesta_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.view_propuesta"):
        return JsonResponse({"error": "No tienes permiso para consultar propuestas."}, status=403)

    propuesta = Propuesta.objects.select_related(
        "version_trabajo", "ejecucion__conjunto",
    ).filter(pk=propuesta_id).first()
    if propuesta is None:
        return JsonResponse({"error": "Propuesta no encontrada."}, status=404)

    version_trabajo = propuesta.version_trabajo
    if version_trabajo is None or version_trabajo.propuesta_id != propuesta.pk:
        return JsonResponse(
            {"error": "La propuesta no tiene una versión disponible."},
            status=409,
        )

    versiones = list(
        VersionHorario.objects.filter(propuesta=propuesta).order_by("-numero")
    )
    numero = request.GET.get("version")
    version = version_trabajo

    if numero is not None:
        version = next((item for item in versiones if str(item.numero) == numero), None)
        if version is None:
            return JsonResponse({"error": "Versión no encontrada."}, status=404)

    es_version_trabajo = version.pk == version_trabajo.pk

    asignaciones = (
        Asignacion.objects.filter(seleccion__version=version)
        .select_related(
            "seleccion__oferta__curso_propuesto__revision",
            "correspondencia__sesion",
            "correspondencia__bloque",
            "franja",
        )
        .order_by(
            "correspondencia__bloque__dia",
            "correspondencia__bloque__inicio",
            "seleccion__oferta__codigo",
        )
    )

    asignaciones = list(asignaciones)
    puede_ajustar = es_version_trabajo and request.user.has_perm(
        "programacion.change_propuesta"
    )
    franjas = list(
        propuesta.ejecucion.conjunto.franjas_utilizables
        .order_by("codigo_salon_copia", "pk")
    ) if puede_ajustar else []

    sesiones = []
    for asignacion in asignaciones:
        oferta = asignacion.seleccion.oferta
        curso = oferta.curso_propuesto
        bloque = asignacion.correspondencia.bloque
        alternativas = {}
        for franja in franjas:
            if (
                franja.salon_id == asignacion.franja.salon_id
                or franja.dia != bloque.dia
                or franja.inicio > bloque.inicio
                or franja.fin < bloque.fin
            ):
                continue

            ocupado = any(
                otra.pk != asignacion.pk
                and otra.franja.salon_id == franja.salon_id
                and otra.correspondencia.bloque.dia == bloque.dia
                and otra.correspondencia.bloque.inicio < bloque.fin
                and bloque.inicio < otra.correspondencia.bloque.fin
                for otra in asignaciones
            )
            if not ocupado:
                alternativas.setdefault(franja.salon_id, {
                    "franja_id": franja.pk,
                    "salon": franja.codigo_salon_copia,
                })
        sesiones.append({
            "id": asignacion.pk,
            "oferta": oferta.codigo,
            "asignatura": curso.denominacion_copia,
            "docente": curso.revision.nombres,
            "grupo": oferta.grupo_copia,
            "sesion": asignacion.correspondencia.sesion.numero,
            "dia": bloque.dia,
            "inicio": bloque.inicio.strftime("%H:%M"),
            "fin": bloque.fin.strftime("%H:%M"),
            "salon": asignacion.franja.codigo_salon_copia,
            "salones_alternativos": list(alternativas.values()),            
        })

    ofertas_seleccionadas = version.selecciones.values("oferta_id")
    pendientes = propuesta.ejecucion.conjunto.ofertas.exclude(
        pk__in=ofertas_seleccionadas,
    ).order_by("codigo").values_list("codigo", flat=True)

    return JsonResponse({
        "id": propuesta.pk,
        "version": version.numero,
        "version_id": version.pk,
        "es_version_trabajo": es_version_trabajo,
        "versiones": [
            {"numero": item.numero}
            for item in versiones
            if item.pk != version_trabajo.pk
        ],
        "estado": version.estado,
        "sesiones": sesiones,
        "pendientes": list(pendientes),
        "puede_ajustar": puede_ajustar,
    })

@require_POST
def ajustar_salon_propuesta(request, propuesta_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.change_propuesta"):
        return JsonResponse({"error": "No tienes permiso para ajustar propuestas."}, status=403)

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    campos = ("version_base_id", "asignacion_id", "franja_id")
    if not isinstance(datos, dict) or any(
        type(datos.get(campo)) is not int or not 1 <= datos[campo] <= 2**63 - 1
        for campo in campos
    ):
        return JsonResponse({"error": "Indica la versión, la sesión y la franja válidas."}, status=400)

    try:
        version = cambiar_salon(
            propuesta_id=propuesta_id,
            version_base_id=datos["version_base_id"],
            asignacion_id=datos["asignacion_id"],
            franja_id=datos["franja_id"],
            usuario=request.user,
        )
    except AjusteHorarioError as error:
        return JsonResponse({"error": str(error)}, status=error.status)

    return JsonResponse({
        "propuesta_id": propuesta_id,
        "version_id": version.pk,
        "version": version.numero,
        "estado": version.estado,
    }, status=201)
@never_cache
@require_GET
def historial_propuestas(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("programacion.view_propuesta"):
        return JsonResponse({"error": "No tienes permiso para consultar propuestas."}, status=403)

    if not Recopilacion.objects.filter(pk=recopilacion_id).exists():
        return JsonResponse({"error": "Recopilación no encontrada."}, status=404)

    propuestas = (
        Propuesta.objects.filter(
            ejecucion__conjunto__recopilacion_id=recopilacion_id,
            ejecucion__solicitado_por=request.user,
            version_trabajo__isnull=False,
        )
        .select_related("ejecucion__conjunto")
        .order_by("-pk")
    )

    return JsonResponse({
        "propuestas": [
            {
                "id": propuesta.pk,
                "conjunto_numero": propuesta.ejecucion.conjunto.numero,
                "creada_en": propuesta.creada_en,
            }
            for propuesta in propuestas
        ],
    })