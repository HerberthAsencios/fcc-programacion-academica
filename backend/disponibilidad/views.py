import json
import csv

from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from datetime import datetime
from django.db.models import OuterRef, Prefetch, Subquery
from .forms import CargaNoLectiva
from .forms import CargaNoLectivaForm
from django.utils import timezone
from programacion.models import EjecucionGeneracion

from .models import Convocado, Declaracion, Recopilacion, RevisionFicha, Asignatura, CursoPropuesto, BloqueHorario, OpcionSemanal,CargaNoLectiva,Auditoria


CAMPOS_EDITABLES = {"contacto": 254, "categoria": 100, "dedicacion": 100}
CAMPOS_RESPUESTA = ("numero", "codigo_docente", "nombres", *CAMPOS_EDITABLES)


def responder_borrador(revision):
    datos = None
    if revision is not None:
        datos = {campo: getattr(revision, campo) for campo in CAMPOS_RESPUESTA}
    return JsonResponse({"borrador": datos})


def ultimo_borrador(revisiones):
    return revisiones.filter(
        estado=RevisionFicha.Estado.BORRADOR,
    ).order_by("-numero").first()


@require_http_methods(["GET", "PUT"])
def borrador_ficha(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    convocado = Convocado.objects.select_related("docente").filter(
        recopilacion_id=recopilacion_id,
        docente__usuario_id=request.user.pk,
        activo=True,
    ).first()
    if convocado is None:
        return JsonResponse({"error": "Convocatoria no encontrada."}, status=404)

    if request.method == "GET":
        revisiones = RevisionFicha.objects.filter(declaracion__convocado=convocado)
        return responder_borrador(ultimo_borrador(revisiones))

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(datos, dict) or datos.keys() != CAMPOS_EDITABLES.keys():
        return JsonResponse(
            {"error": "Envía contacto, categoria y dedicacion."},
            status=400,
        )

    for campo, limite in CAMPOS_EDITABLES.items():
        valor = datos[campo]
        if not isinstance(valor, str) or len(valor.strip()) > limite:
            return JsonResponse({"error": f"Valor inválido para {campo}."}, status=400)
        datos[campo] = valor.strip()

    with transaction.atomic():
        recopilacion = Recopilacion.objects.select_for_update().get(
            pk=recopilacion_id
        )
        if recopilacion.estado != Recopilacion.Estado.ABIERTA:
            return JsonResponse({"error": "La recopilación no está abierta."}, status=409)

        ficha, _ = Declaracion.objects.get_or_create(convocado=convocado)
        revision = ultimo_borrador(ficha.revisiones)
        if revision is None:
            ultimo_numero = (
                ficha.revisiones.order_by("-numero")
                .values_list("numero", flat=True)
                .first()
            )
            revision = RevisionFicha(
                declaracion=ficha,
                numero=(ultimo_numero or 0) + 1,
            )

        revision.codigo_docente = convocado.docente.codigo
        revision.nombres = convocado.docente.nombres
        revision.contacto = datos["contacto"]
        revision.categoria = datos["categoria"]
        revision.dedicacion = datos["dedicacion"]
        revision.save()

    return responder_borrador(revision)

@never_cache
@require_http_methods(["GET", "POST"])
def sesion(request):
    if request.method == "POST":
        if request.content_type != "application/json":
            return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

        try:
            datos = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "JSON inválido."}, status=400)

        if not isinstance(datos, dict):
            return JsonResponse({"error": "Envía usuario y contraseña."}, status=400)

        usuario = datos.get("usuario")
        clave = datos.get("clave")
        if not isinstance(usuario, str) or not isinstance(clave, str) or not usuario or not clave:
            return JsonResponse({"error": "Envía usuario y contraseña."}, status=400)

        cuenta = authenticate(request, username=usuario, password=clave)
        if cuenta is None:
            return JsonResponse({"error": "Usuario o contraseña incorrectos."}, status=401)

        login(request, cuenta)

    convocatorias = []
    if request.user.is_authenticated:
        registros = Convocado.objects.filter(
            docente__usuario_id=request.user.pk,
            activo=True,
        ).select_related("recopilacion__periodo")

        convocatorias = [
            {
                "id": registro.recopilacion_id,
                "periodo": registro.recopilacion.periodo.denominacion,
                "estado": registro.recopilacion.estado,
            }
            for registro in registros
        ]

    recopilaciones_gestion = None
    if request.user.has_perm("disponibilidad.view_convocado"):
        recopilaciones_gestion = [
            {"id": registro.pk, "periodo": registro.periodo.denominacion}
            for registro in Recopilacion.objects.select_related("periodo")
            .order_by("periodo__codigo")
        ]
    return JsonResponse({
        "autenticado": request.user.is_authenticated,
        "csrfToken": get_token(request),
        "convocatorias": convocatorias,
        "recopilaciones_gestion": recopilaciones_gestion,
        "puede_cambiar_estado": request.user.has_perm("disponibilidad.change_recopilacion"),
    })


@require_http_methods(["GET"])
def listar_asignaturas(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    convocado = Convocado.objects.filter(
        recopilacion_id=recopilacion_id,
        docente__usuario_id=request.user.pk,
        activo=True,
    ).exists()
    if not convocado:
        return JsonResponse({"error": "Convocatoria no encontrada."}, status=404)

    asignaturas = Asignatura.objects.filter(activo=True).order_by(
        "denominacion", "codigo"
    ).values("id", "codigo", "denominacion")

    return JsonResponse({"asignaturas": list(asignaturas)})

@require_http_methods(["GET", "POST"])
def cursos_borrador(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    convocado = Convocado.objects.filter(
        recopilacion_id=recopilacion_id,
        docente__usuario_id=request.user.pk,
        activo=True,
    ).first()
    if convocado is None:
        return JsonResponse({"error": "Convocatoria no encontrada."}, status=404)

    revisiones = RevisionFicha.objects.filter(declaracion__convocado=convocado)

    if request.method == "GET":
        borrador = ultimo_borrador(revisiones)
        cursos = []
        if borrador is not None:
            cursos = list(borrador.cursos_propuestos.order_by("prioridad").values(
                "id", "asignatura_id", "prioridad", "denominacion_copia",
            ))
        return JsonResponse({"cursos": cursos})

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(datos, dict):
        return JsonResponse({"error": "Envía la asignatura y la prioridad."}, status=400)

    asignatura_id = datos.get("asignatura_id")
    prioridad = datos.get("prioridad")
    if type(asignatura_id) is not int or asignatura_id < 1:
        return JsonResponse({"error": "Selecciona una asignatura válida."}, status=400)
    if type(prioridad) is not int or not 1 <= prioridad <= 2_147_483_647:
        return JsonResponse({"error": "La prioridad debe ser un entero positivo."}, status=400)

    with transaction.atomic():
        recopilacion = Recopilacion.objects.select_for_update().get(pk=recopilacion_id)
        if recopilacion.estado != Recopilacion.Estado.ABIERTA:
            return JsonResponse({"error": "La recopilación no está abierta."}, status=409)

        borrador = ultimo_borrador(revisiones)
        if borrador is None:
            return JsonResponse({"error": "Guarda primero los datos generales."}, status=409)

        asignatura = Asignatura.objects.filter(pk=asignatura_id, activo=True).first()
        if asignatura is None:
            return JsonResponse({"error": "La asignatura no está disponible."}, status=404)

        if borrador.cursos_propuestos.filter(asignatura=asignatura).exists():
            return JsonResponse({"error": "La asignatura ya está en el borrador."}, status=409)
        if borrador.cursos_propuestos.filter(prioridad=prioridad).exists():
            return JsonResponse({"error": "Esa prioridad ya está en uso."}, status=409)

        curso = borrador.cursos_propuestos.create(
            asignatura=asignatura,
            prioridad=prioridad,
            denominacion_copia=asignatura.denominacion,
        )

    return JsonResponse({
        "curso": {
            "id": curso.pk,
            "asignatura_id": curso.asignatura_id,
            "prioridad": curso.prioridad,
            "denominacion_copia": curso.denominacion_copia,
        },
    }, status=201)

def validar_bloques(datos):
    if not isinstance(datos, dict):
        raise ValueError("Envía los bloques de la opción semanal.")

    bloques = datos.get("bloques")
    if not isinstance(bloques, list) or not bloques:
        raise ValueError("Agrega al menos un bloque a la opción.")

    resultado = []
    for bloque in bloques:
        if not isinstance(bloque, dict):
            raise ValueError("Cada bloque debe tener día, inicio y fin.")

        dia = bloque.get("dia")
        if type(dia) is not int or not 1 <= dia <= 6:
            raise ValueError("Selecciona un día de lunes a sábado.")

        try:
            inicio = datetime.strptime(bloque.get("inicio"), "%H:%M").time()
            fin = datetime.strptime(bloque.get("fin"), "%H:%M").time()
        except (TypeError, ValueError):
            raise ValueError("Ingresa las horas en formato HH:MM.") from None

        if inicio >= fin:
            raise ValueError("La hora de fin debe ser posterior a la de inicio.")

        resultado.append((dia, inicio, fin))

    resultado.sort()
    for anterior, actual in zip(resultado, resultado[1:]):
        if anterior[0] == actual[0] and actual[1] < anterior[2]:
            raise ValueError("Hay bloques que se superponen dentro de la opción.")

    return resultado


def datos_opcion(opcion, bloques):
    return {
        "id": opcion.pk,
        "numero": opcion.numero,
        "bloques": [
            {
                "dia": bloque.dia,
                "inicio": bloque.inicio.strftime("%H:%M"),
                "fin": bloque.fin.strftime("%H:%M"),
            }
            for bloque in bloques
        ],
    }


@require_http_methods(["GET", "POST", "PUT"])
@transaction.atomic
def opciones_curso(request, recopilacion_id, curso_id, opcion_id=None):
    if opcion_id is None and request.method == "PUT":
        return HttpResponseNotAllowed(["GET", "POST"])
    if opcion_id is not None and request.method != "PUT":
        return HttpResponseNotAllowed(["PUT"])

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    convocado = Convocado.objects.filter(
        recopilacion_id=recopilacion_id,
        docente__usuario_id=request.user.pk,
        activo=True,
    ).first()
    if convocado is None:
        return JsonResponse({"error": "Convocatoria no encontrada."}, status=404)

    if request.method != "GET":
        recopilacion = Recopilacion.objects.select_for_update().get(pk=recopilacion_id)
        if recopilacion.estado != Recopilacion.Estado.ABIERTA:
            return JsonResponse({"error": "La recopilación no está abierta."}, status=409)

    borrador = ultimo_borrador(
        RevisionFicha.objects.filter(declaracion__convocado=convocado)
    )
    curso = CursoPropuesto.objects.filter(pk=curso_id, revision=borrador).first()
    if curso is None:
        return JsonResponse({"error": "Curso no encontrado en tu borrador."}, status=404)

    if request.method == "GET":
        opciones = curso.opciones.order_by("numero").prefetch_related(
            Prefetch("bloques", queryset=BloqueHorario.objects.order_by("numero"))
        )
        return JsonResponse({
            "opciones": [datos_opcion(opcion, opcion.bloques.all()) for opcion in opciones],
        })

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    try:
        bloques = validar_bloques(datos)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    if opcion_id is None:
        ultimo_numero = (
            curso.opciones.order_by("-numero")
            .values_list("numero", flat=True)
            .first()
        )
        opcion = curso.opciones.create(numero=(ultimo_numero or 0) + 1)
        estado = 201
    else:
        opcion = curso.opciones.filter(pk=opcion_id).first()
        if opcion is None:
            return JsonResponse({"error": "Opción no encontrada en este curso."}, status=404)
        opcion.bloques.all().delete()
        estado = 200

    registros = [
        BloqueHorario(opcion=opcion, numero=numero, dia=dia, inicio=inicio, fin=fin)
        for numero, (dia, inicio, fin) in enumerate(bloques, start=1)
    ]
    BloqueHorario.objects.bulk_create(registros)

    return JsonResponse({"opcion": datos_opcion(opcion, registros)}, status=estado)

def datos_carga_no_lectiva(registro):
    return {
        "id": registro.pk,
        "tipo": registro.tipo,
        "actividad": registro.actividad,
        "horas": format(registro.horas, ".2f"),
    }


@require_http_methods(["GET", "POST"])
@transaction.atomic
def carga_no_lectiva(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    convocado = Convocado.objects.filter(
        recopilacion_id=recopilacion_id,
        docente__usuario_id=request.user.pk,
        activo=True,
    ).first()
    if convocado is None:
        return JsonResponse({"error": "Convocatoria no encontrada."}, status=404)

    if request.method == "POST":
        recopilacion = Recopilacion.objects.select_for_update().get(pk=recopilacion_id)
        if recopilacion.estado != Recopilacion.Estado.ABIERTA:
            return JsonResponse({"error": "La recopilación no está abierta."}, status=409)

    borrador = ultimo_borrador(
        RevisionFicha.objects.filter(declaracion__convocado=convocado)
    )

    if request.method == "GET":
        actividades = []
        if borrador is not None:
            actividades = [
                datos_carga_no_lectiva(registro)
                for registro in borrador.cargas_no_lectivas.order_by("id")
            ]
        return JsonResponse({"actividades": actividades})

    if borrador is None:
        return JsonResponse({"error": "Guarda primero los datos generales."}, status=409)

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(datos, dict) or not isinstance(datos.get("actividad"), str):
        return JsonResponse({"error": "Envía el tipo, la actividad y las horas."}, status=400)

    formulario = CargaNoLectivaForm(datos)
    if not formulario.is_valid():
        return JsonResponse({
            "error": "Revisa el tipo, la descripción y las horas de la actividad.",
            "campos": formulario.errors.get_json_data(),
        }, status=400)

    registro = borrador.cargas_no_lectivas.create(**formulario.cleaned_data)
    return JsonResponse({"actividad": datos_carga_no_lectiva(registro)}, status=201)

def datos_envio(revision):
    return {
        "numero": revision.numero,
        "enviada_en": revision.enviada_en.isoformat(),
    }


def validar_ficha_para_envio(revision):
    if not revision.codigo_docente.strip() or not revision.nombres.strip():
        raise ValueError("Falta la identificación del docente.")

    cursos = list(
        revision.cursos_propuestos.order_by("prioridad")
        .prefetch_related("opciones__bloques")
    )
    if not cursos:
        raise ValueError("Agrega al menos un curso antes de enviar la ficha.")

    fecha_base = datetime.min.date()

    for curso in cursos:
        opciones = list(curso.opciones.all())
        nombre = curso.denominacion_copia
        if not opciones:
            raise ValueError(f"Agrega una opción semanal para {nombre}.")

        duraciones_esperadas = None
        for opcion in opciones:
            bloques = list(opcion.bloques.all())
            try:
                validar_bloques(datos_opcion(opcion, bloques))
            except ValueError as error:
                raise ValueError(f"{nombre}, opción {opcion.numero}: {error}") from error

            duraciones = sorted(
                datetime.combine(fecha_base, bloque.fin)
                - datetime.combine(fecha_base, bloque.inicio)
                for bloque in bloques
            )
            if duraciones_esperadas is None:
                duraciones_esperadas = duraciones
            elif duraciones != duraciones_esperadas:
                raise ValueError(
                    f"Las opciones de {nombre} deben tener la misma cantidad "
                    "de bloques y las mismas duraciones."
                )


@require_http_methods(["GET", "POST"])
@transaction.atomic
def envio_ficha(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    convocado = Convocado.objects.filter(
        recopilacion_id=recopilacion_id,
        docente__usuario_id=request.user.pk,
        activo=True,
    ).first()
    if convocado is None:
        return JsonResponse({"error": "Convocatoria no encontrada."}, status=404)

    revisiones = RevisionFicha.objects.filter(declaracion__convocado=convocado)

    if request.method == "GET":
        enviada = revisiones.filter(
            estado=RevisionFicha.Estado.ENVIADA,
            enviada_en__isnull=False,
        ).order_by("-numero").first()
        return JsonResponse({"enviada": datos_envio(enviada) if enviada else None})

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    numero = datos.get("numero") if isinstance(datos, dict) else None
    if type(numero) is not int or not 1 <= numero <= 2_147_483_647:
        return JsonResponse({"error": "Indica el número de revisión."}, status=400)

    recopilacion = Recopilacion.objects.select_for_update().get(pk=recopilacion_id)
    revision = revisiones.filter(numero=numero).first()

    if revision is not None and revision.estado == RevisionFicha.Estado.ENVIADA:
        return JsonResponse({"enviada": datos_envio(revision)})

    if recopilacion.estado != Recopilacion.Estado.ABIERTA:
        return JsonResponse({"error": "La recopilación no está abierta."}, status=409)

    borrador = ultimo_borrador(revisiones)
    if borrador is None or borrador.numero != numero:
        return JsonResponse(
            {"error": "El borrador cambió. Recarga la ficha antes de enviarla."},
            status=409,
        )

    try:
        validar_ficha_para_envio(borrador)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    borrador.estado = RevisionFicha.Estado.ENVIADA
    borrador.enviada_en = timezone.now()
    borrador.save(update_fields=["estado", "enviada_en"])

    return JsonResponse({"enviada": datos_envio(borrador)})

@require_http_methods(["POST"])
@transaction.atomic
def nueva_revision(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    convocado = Convocado.objects.filter(
        recopilacion_id=recopilacion_id,
        docente__usuario_id=request.user.pk,
        activo=True,
    ).first()
    if convocado is None:
        return JsonResponse({"error": "Convocatoria no encontrada."}, status=404)

    recopilacion = Recopilacion.objects.select_for_update().get(pk=recopilacion_id)
    if recopilacion.estado != Recopilacion.Estado.ABIERTA:
        return JsonResponse({"error": "La recopilación no está abierta."}, status=409)

    revisiones = RevisionFicha.objects.filter(declaracion__convocado=convocado)
    borrador = ultimo_borrador(revisiones)
    if borrador is not None:
        return responder_borrador(borrador)

    enviada = revisiones.filter(
        estado=RevisionFicha.Estado.ENVIADA,
        enviada_en__isnull=False,
    ).order_by("-numero").first()
    if enviada is None:
        return JsonResponse({"error": "Todavía no hay una ficha enviada."}, status=409)

    nueva = RevisionFicha.objects.create(
        declaracion=enviada.declaracion,
        numero=enviada.numero + 1,
        codigo_docente=enviada.codigo_docente,
        nombres=enviada.nombres,
        contacto=enviada.contacto,
        categoria=enviada.categoria,
        dedicacion=enviada.dedicacion,
    )

    for curso in enviada.cursos_propuestos.prefetch_related("opciones__bloques"):
        copia_curso = nueva.cursos_propuestos.create(
            asignatura_id=curso.asignatura_id,
            prioridad=curso.prioridad,
            denominacion_copia=curso.denominacion_copia,
            plan_ref=curso.plan_ref,
            ciclo_ref=curso.ciclo_ref,
            escuela_ref=curso.escuela_ref,
        )

        for opcion in curso.opciones.all():
            copia_opcion = copia_curso.opciones.create(numero=opcion.numero)
            BloqueHorario.objects.bulk_create([
                BloqueHorario(
                    opcion=copia_opcion,
                    numero=bloque.numero,
                    dia=bloque.dia,
                    inicio=bloque.inicio,
                    fin=bloque.fin,
                )
                for bloque in opcion.bloques.all()
            ])

    CargaNoLectiva.objects.bulk_create([
        CargaNoLectiva(revision=nueva, **actividad)
        for actividad in enviada.cargas_no_lectivas.values("tipo", "actividad", "horas")
    ])

    return responder_borrador(nueva)

@require_http_methods(["GET"])
def seguimiento_recopilacion(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("disponibilidad.view_convocado"):
        return JsonResponse({"error": "No tienes permiso para consultar el seguimiento."}, status=403)

    recopilacion = Recopilacion.objects.select_related("periodo").filter(
        pk=recopilacion_id,
    ).first()
    if recopilacion is None:
        return JsonResponse({"error": "Recopilación no encontrada."}, status=404)

    ultimo_envio = RevisionFicha.objects.filter(
        declaracion__convocado_id=OuterRef("pk"),
        estado=RevisionFicha.Estado.ENVIADA,
        enviada_en__isnull=False,
    ).order_by("-numero")

    convocados = (
        Convocado.objects.filter(recopilacion=recopilacion, activo=True)
        .select_related("docente")
        .annotate(
            revision_enviada=Subquery(ultimo_envio.values("numero")[:1]),
            fecha_envio=Subquery(ultimo_envio.values("enviada_en")[:1]),
        )
        .order_by("docente__nombres", "docente__codigo")
    )

    docentes = [
        {
            "codigo": convocado.docente.codigo,
            "nombres": convocado.docente.nombres,
            "estado": "RECIBIDA" if convocado.revision_enviada is not None else "PENDIENTE",
            "revision_enviada": convocado.revision_enviada,
            "fecha_envio": convocado.fecha_envio,
        }
        for convocado in convocados
    ]
    recibidas = sum(docente["estado"] == "RECIBIDA" for docente in docentes)
    puede_generar = request.user.has_perms([
        "programacion.add_ejecuciongeneracion",
        "programacion.view_ejecuciongeneracion",
    ])
    conjuntos_congelados = []
    if puede_generar:
        conjuntos_congelados = list(
            recopilacion.conjuntos_insumos.filter(estado="CONGELADO")
            .order_by("-numero")
            .values("id", "numero")
        )
    ultima_ejecucion_id = None
    if puede_generar:
        ultima_ejecucion_id = (
            EjecucionGeneracion.objects.filter(
                conjunto__recopilacion=recopilacion,
                solicitado_por=request.user,
            )
            .order_by("-pk")
            .values_list("pk", flat=True)
            .first()
        )

    return JsonResponse({
        "periodo": recopilacion.periodo.denominacion,
        "estado": recopilacion.estado,
        "total": len(docentes),
        "recibidas": recibidas,
        "pendientes": len(docentes) - recibidas,
        "docentes": docentes,
        "puede_generar": puede_generar,
        "conjuntos_congelados": conjuntos_congelados, 
        "ultima_ejecucion_id": ultima_ejecucion_id,
    })

@require_http_methods(["POST"])
@transaction.atomic
def cambiar_estado_recopilacion(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("disponibilidad.change_recopilacion"):
        return JsonResponse(
            {"error": "No tienes permiso para cambiar el estado."},
            status=403,
        )

    if request.content_type != "application/json":
        return JsonResponse({"error": "Envía los datos como JSON."}, status=415)

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(datos, dict):
        return JsonResponse({"error": "Indica la acción que quieres realizar."}, status=400)

    estados = Recopilacion.Estado
    transiciones = {
        "ABRIR": (estados.PREPARACION, estados.ABIERTA),
        "CERRAR": (estados.ABIERTA, estados.CERRADA),
        "REABRIR": (estados.CERRADA, estados.ABIERTA),
    }

    accion = datos.get("accion")
    if not isinstance(accion, str) or accion not in transiciones:
        return JsonResponse({"error": "La acción no es válida."}, status=400)

    motivo = datos.get("motivo", "")
    if accion == "REABRIR" and (not isinstance(motivo, str) or not motivo.strip()):
        return JsonResponse({"error": "Indica el motivo de la reapertura."}, status=400)

    recopilacion = Recopilacion.objects.select_for_update().filter(
        pk=recopilacion_id,
    ).first()
    if recopilacion is None:
        return JsonResponse({"error": "Recopilación no encontrada."}, status=404)

    estado_anterior, estado_nuevo = transiciones[accion]
    if recopilacion.estado != estado_anterior:
        return JsonResponse(
            {"error": "La acción no corresponde al estado actual de la recopilación."},
            status=409,
        )

    ahora = timezone.now()
    recopilacion.estado = estado_nuevo
    if accion == "ABRIR":
        recopilacion.apertura_en = ahora
        recopilacion.cierre_en = None
    elif accion == "CERRAR":
        recopilacion.cierre_en = ahora
    else:
        recopilacion.cierre_en = None

    recopilacion.save(update_fields=["estado", "apertura_en", "cierre_en"])

    detalle = {
        "estado_anterior": estado_anterior,
        "estado_nuevo": estado_nuevo,
    }
    if accion == "REABRIR":
        detalle["motivo"] = motivo.strip()

    Auditoria.objects.create(
        usuario=request.user,
        operacion=f"{accion}_RECOPILACION",
        periodo_id=recopilacion.periodo_id,
        objeto_tipo="recopilacion",
        objeto_id=recopilacion.pk,
        detalle=detalle,
    )

    return JsonResponse({"estado": recopilacion.estado})
def texto_csv(valor):
    if valor.startswith(("\t", "\r", "\n")) or valor.lstrip().startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + valor
    return valor


@require_http_methods(["GET"])
def exportar_disponibilidad(request, recopilacion_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión."}, status=401)

    if not request.user.has_perm("disponibilidad.view_convocado"):
        return JsonResponse({"error": "No tienes permiso para exportar."}, status=403)

    recopilacion = Recopilacion.objects.select_related("periodo").filter(
        pk=recopilacion_id,
    ).first()
    if recopilacion is None:
        return JsonResponse({"error": "Recopilación no encontrada."}, status=404)

    ultimas_revisiones = (
        RevisionFicha.objects.filter(
            declaracion__convocado__recopilacion=recopilacion,
            declaracion__convocado__activo=True,
            estado=RevisionFicha.Estado.ENVIADA,
            enviada_en__isnull=False,
        )
        .order_by("declaracion_id", "-numero")
        .distinct("declaracion_id")
        .values("pk")
    )

    bloques = (
        BloqueHorario.objects.filter(
            opcion__curso_propuesto__revision_id__in=Subquery(ultimas_revisiones)
        )
        .select_related(
            "opcion__curso_propuesto__revision",
            "opcion__curso_propuesto__asignatura",
        )
        .order_by(
            "opcion__curso_propuesto__revision__codigo_docente",
            "opcion__curso_propuesto__prioridad",
            "opcion__numero",
            "numero",
        )
    )

    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = (
        f'attachment; filename="disponibilidad-{recopilacion.pk}.csv"'
    )
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta, delimiter=";")

    escritor.writerow([
        "periodo", "codigo_docente", "docente", "revision",
        "codigo_asignatura", "asignatura", "prioridad",
        "opcion_id", "opcion", "bloque_id", "bloque", "dia", "inicio", "fin",
    ])

    dias = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")

    for bloque in bloques.iterator():
        opcion = bloque.opcion
        curso = opcion.curso_propuesto
        revision = curso.revision
        escritor.writerow([
            texto_csv(recopilacion.periodo.codigo),
            texto_csv(revision.codigo_docente),
            texto_csv(revision.nombres),
            revision.numero,
            texto_csv(curso.asignatura.codigo),
            texto_csv(curso.denominacion_copia),
            curso.prioridad,
            opcion.pk,
            opcion.numero,
            bloque.pk,
            bloque.numero,
            dias[bloque.dia - 1],
            bloque.inicio.strftime("%H:%M"),
            bloque.fin.strftime("%H:%M"),
        ])

    return respuesta