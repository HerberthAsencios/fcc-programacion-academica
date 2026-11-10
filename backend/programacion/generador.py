from dataclasses import dataclass
from itertools import combinations, product
from time import monotonic

from disponibilidad.models import BloqueHorario

from .models import ConjuntoInsumos, FranjaUtilizable, SesionRequerida


@dataclass(frozen=True)
class AsignacionCandidata:
    sesion: SesionRequerida
    bloque: BloqueHorario
    franja: FranjaUtilizable
    docente_id: int
    grupo_id: int
    opcion_habilitada_id: int


def hay_cruce(primera, segunda):
    a, b = primera.bloque, segunda.bloque
    mismo_recurso = (
        primera.docente_id == segunda.docente_id
        or primera.grupo_id == segunda.grupo_id
        or primera.franja.salon_id == segunda.franja.salon_id
    )
    return (
        mismo_recurso
        and a.dia == b.dia
        and a.inicio < b.fin
        and b.inicio < a.fin
    )


def planes_de_oferta(oferta, franjas):
    docente_id = oferta.curso_propuesto.revision.declaracion.convocado.docente_id

    for opcion in sorted(oferta.opciones_habilitadas.all(), key=lambda item: item.pk):
        correspondencias = sorted(
            opcion.correspondencias.all(),
            key=lambda registro: registro.sesion.numero,
        )
        if not correspondencias:
            continue

        alternativas = []
        for registro in correspondencias:
            bloque = registro.bloque
            por_salon = {}
            for franja in franjas:
                if (
                    franja.dia == bloque.dia
                    and franja.inicio <= bloque.inicio
                    and franja.fin >= bloque.fin
                ):
                    por_salon.setdefault(franja.salon_id, franja)

            alternativas.append([
                AsignacionCandidata(
                    sesion=registro.sesion,
                    bloque=bloque,
                    franja=franja,
                    docente_id=docente_id,
                    grupo_id=oferta.grupo_id,
                    opcion_habilitada_id=opcion.pk,
                )
                for franja in por_salon.values()
            ])

        yield from product(*alternativas)

    # También se puede dejar la oferta completa pendiente.
    yield ()


def generar_horario(conjunto, max_intentos=10_000, limite_ms=None):
    vencimiento = None if limite_ms is None else monotonic() + limite_ms / 1000

    if conjunto.estado != ConjuntoInsumos.Estado.CONGELADO:
        raise ValueError("Congela el conjunto antes de generar el horario.")

    ofertas = list(
        conjunto.ofertas.select_related("curso_propuesto__revision__declaracion__convocado")
        .prefetch_related(
            "opciones_habilitadas__correspondencias__bloque",
            "opciones_habilitadas__correspondencias__sesion",
        )
        .order_by("codigo", "pk")
    )
    if not ofertas:
        raise ValueError("El conjunto no tiene ofertas para programar.")

    franjas = list(conjunto.franjas_utilizables.order_by("codigo_salon_copia", "pk"))
    seleccion = {}
    mejor = {}
    intentos = 0
    pila = [iter(planes_de_oferta(ofertas[0], franjas))]

    while pila and intentos < max_intentos:
        if vencimiento is not None and monotonic() >= vencimiento:
            break   
        nivel = len(pila) - 1
        oferta = ofertas[nivel]
        seleccion.pop(oferta.pk, None)

        plan = next(pila[-1], None)
        if plan is None:
            pila.pop()
            continue

        intentos += 1
        ocupadas = [asignacion for grupo in seleccion.values() for asignacion in grupo]
        if any(hay_cruce(a, b) for a, b in combinations(plan, 2)) or any(
            hay_cruce(nueva, anterior) for nueva in plan for anterior in ocupadas
        ):
            continue

        if plan:
            seleccion[oferta.pk] = plan
            if len(seleccion) > len(mejor):
                mejor = seleccion.copy()

        if len(mejor) == len(ofertas):
            break

        ofertas_restantes = len(ofertas) - nivel - 1
        if ofertas_restantes and len(seleccion) + ofertas_restantes > len(mejor):
            pila.append(iter(planes_de_oferta(ofertas[nivel + 1], franjas)))

    pendientes = [oferta.codigo for oferta in ofertas if oferta.pk not in mejor]
    if not pendientes:
        estado = "COMPLETA"
    elif mejor:
        estado = "PARCIAL"
    else:
        estado = "SIN_RESULTADO"

    return {
        "estado": estado,
        "asignaciones": mejor,
        "pendientes": pendientes,
        "intentos": intentos,
        "limite_alcanzado": bool(
            pendientes and pila and (
                intentos >= max_intentos
                or (vencimiento is not None and monotonic() >= vencimiento)
            )
        ),    }
