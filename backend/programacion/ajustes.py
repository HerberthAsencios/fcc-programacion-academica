from django.db import transaction

from disponibilidad.models import Auditoria

from .ejecuciones import guardar_selecciones
from .generador import AsignacionCandidata
from .models import Asignacion, Propuesta
from .models import Asignacion, CorrespondenciaSesion, Propuesta


class AjusteHorarioError(ValueError):
    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.status = status


@transaction.atomic
def _cargar_version_de_trabajo(propuesta_id, version_base_id):
    propuesta = Propuesta.objects.select_for_update().filter(pk=propuesta_id).first()
    if propuesta is None:
        raise AjusteHorarioError("Propuesta no encontrada.", status=404)

    base = propuesta.version_trabajo
    if base is None or base.propuesta_id != propuesta.pk or base.pk != version_base_id:
        raise AjusteHorarioError(
            "La versión de trabajo cambió. Vuelve a consultar la propuesta.",
            status=409,
        )

    conjunto = propuesta.ejecucion.conjunto
    filas = list(
        Asignacion.objects.filter(seleccion__version=base).select_related(
            "seleccion__oferta__curso_propuesto__revision__declaracion__convocado",
            "correspondencia__sesion",
            "correspondencia__bloque",
            "franja",
        )
    )
    return propuesta, base, conjunto, filas


@transaction.atomic
def cambiar_salon(propuesta_id, version_base_id, asignacion_id, franja_id, usuario):
    propuesta, base, conjunto, filas = _cargar_version_de_trabajo(
        propuesta_id, version_base_id,
    )
    original = next((fila for fila in filas if fila.pk == asignacion_id), None)
    if original is None:
        raise AjusteHorarioError("La sesión no pertenece a esta versión.", status=404)

    bloque = original.correspondencia.bloque
    destino = conjunto.franjas_utilizables.filter(
        pk=franja_id,
        dia=bloque.dia,
        inicio__lte=bloque.inicio,
        fin__gte=bloque.fin,
    ).first()
    if destino is None:
        raise AjusteHorarioError("El salón no está disponible para todo el bloque.")
    if destino.salon_id == original.franja.salon_id:
        raise AjusteHorarioError("Selecciona un salón distinto al actual.", status=409)

    planes = {}
    for fila in filas:
        oferta = fila.seleccion.oferta
        docente_id = oferta.curso_propuesto.revision.declaracion.convocado.docente_id
        planes.setdefault(oferta.pk, []).append(AsignacionCandidata(
            sesion=fila.correspondencia.sesion,
            bloque=fila.correspondencia.bloque,
            franja=destino if fila.pk == original.pk else fila.franja,
            docente_id=docente_id,
            grupo_id=oferta.grupo_id,
            opcion_habilitada_id=fila.seleccion.opcion_habilitada_id,
        ))

    nueva = _guardar_version(propuesta, base, conjunto, planes, usuario)

    Auditoria.objects.create(
        usuario=usuario,
        operacion="CAMBIAR_SALON",
        periodo_id=conjunto.recopilacion.periodo_id,
        objeto_tipo="propuesta",
        objeto_id=propuesta.pk,
        detalle={
            "version_base_id": base.pk,
            "version_nueva_id": nueva.pk,
            "asignacion_id": original.pk,
            "salon_anterior": original.franja.codigo_salon_copia,
            "salon_nuevo": destino.codigo_salon_copia,
        },
    )



    return nueva
def _guardar_version(propuesta, base, conjunto, planes, usuario):
    ultimo_numero = propuesta.versiones.order_by("-numero").values_list(
        "numero", flat=True,
    ).first()

    nueva = propuesta.versiones.create(
        numero=ultimo_numero + 1,
        version_origen=base,
        estado=base.estado,
        creado_por=usuario,
    )
    try:
        guardar_selecciones(nueva, conjunto, planes)
    except ValueError as error:
        raise AjusteHorarioError(str(error), status=409) from error

    propuesta.version_trabajo = nueva
    propuesta.save(update_fields=["version_trabajo"])
    return nueva

@transaction.atomic
def cambiar_opcion(
    propuesta_id, version_base_id, oferta_id, opcion_habilitada_id,
    franjas_por_sesion, usuario,
):
    propuesta, base, conjunto, filas = _cargar_version_de_trabajo(
        propuesta_id, version_base_id,
    )

    original = next((fila for fila in filas if fila.seleccion.oferta_id == oferta_id), None)
    if original is None:
        raise AjusteHorarioError(
            "La oferta no está asignada en esta versión.", status=404,
        )

    opcion_anterior_id = original.seleccion.opcion_habilitada_id
    if opcion_habilitada_id == opcion_anterior_id:
        raise AjusteHorarioError("Selecciona una opción distinta a la actual.", status=409)

    correspondencias = list(
        CorrespondenciaSesion.objects.filter(
            opcion_habilitada_id=opcion_habilitada_id,
            opcion_habilitada__oferta_id=oferta_id,
        ).select_related("sesion", "bloque")
    )
    if not correspondencias:
        raise AjusteHorarioError(
            "La opción no está habilitada para esta oferta.", status=404,
        )

    sesiones = {item.sesion_id for item in correspondencias}
    if set(franjas_por_sesion) != sesiones:
        raise AjusteHorarioError("Indica una franja de salón para cada sesión de la opción.")

    franjas = conjunto.franjas_utilizables.in_bulk(set(franjas_por_sesion.values()))
    oferta = original.seleccion.oferta
    docente_id = oferta.curso_propuesto.revision.declaracion.convocado.docente_id
    reemplazo = []

    for item in correspondencias:
        bloque = item.bloque
        franja = franjas.get(franjas_por_sesion[item.sesion_id])
        if (
            franja is None
            or franja.dia != bloque.dia
            or franja.inicio > bloque.inicio
            or franja.fin < bloque.fin
        ):
            raise AjusteHorarioError(
                "La franja elegida debe cubrir todo el bloque de la sesión."
            )

        reemplazo.append(AsignacionCandidata(
            sesion=item.sesion,
            bloque=bloque,
            franja=franja,
            docente_id=docente_id,
            grupo_id=oferta.grupo_id,
            opcion_habilitada_id=opcion_habilitada_id,
        ))

    planes = {oferta_id: reemplazo}
    for fila in filas:
        otra_oferta = fila.seleccion.oferta
        if otra_oferta.pk == oferta_id:
            continue

        planes.setdefault(otra_oferta.pk, []).append(AsignacionCandidata(
            sesion=fila.correspondencia.sesion,
            bloque=fila.correspondencia.bloque,
            franja=fila.franja,
            docente_id=otra_oferta.curso_propuesto.revision.declaracion.convocado.docente_id,
            grupo_id=otra_oferta.grupo_id,
            opcion_habilitada_id=fila.seleccion.opcion_habilitada_id,
        ))

    nueva = _guardar_version(propuesta, base, conjunto, planes, usuario)

    Auditoria.objects.create(
        usuario=usuario,
        operacion="CAMBIAR_OPCION",
        periodo_id=conjunto.recopilacion.periodo_id,
        objeto_tipo="propuesta",
        objeto_id=propuesta.pk,
        detalle={
            "version_base_id": base.pk,
            "version_nueva_id": nueva.pk,
            "oferta_id": oferta_id,
            "opcion_anterior_id": opcion_anterior_id,
            "opcion_nueva_id": opcion_habilitada_id,
        },
    )
    return nueva