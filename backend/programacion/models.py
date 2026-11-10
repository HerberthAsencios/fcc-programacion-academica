from django.conf import settings
from django.db import models


class ConjuntoInsumos(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        CONGELADO = "CONGELADO", "Congelado"

    recopilacion = models.ForeignKey(
        "disponibilidad.Recopilacion",
        on_delete=models.PROTECT,
        related_name="conjuntos_insumos",
    )
    numero = models.PositiveIntegerField()
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    congelado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recopilacion", "numero"],
                name="programacion_conjunto_numero_unico",
            ),
        ]


class InsumoRevision(models.Model):
    conjunto = models.ForeignKey(
        ConjuntoInsumos,
        on_delete=models.PROTECT,
        related_name="insumos_revision",
    )
    revision = models.ForeignKey(
        "disponibilidad.RevisionFicha",
        on_delete=models.PROTECT,
        related_name="insumos_programacion",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conjunto", "revision"],
                name="programacion_insumo_revision_unico",
            ),
        ]

class Grupo(models.Model):
    periodo = models.ForeignKey(
        "disponibilidad.Periodo",
        on_delete=models.PROTECT,
        related_name="grupos_programacion",
    )
    codigo = models.CharField(max_length=30)
    denominacion = models.CharField(max_length=150)
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "codigo"],
                name="programacion_grupo_codigo_unico",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.denominacion}"


class Salon(models.Model):
    codigo = models.CharField(max_length=30, unique=True)
    denominacion = models.CharField(max_length=150)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.codigo} · {self.denominacion}"


class FranjaUtilizable(models.Model):
    conjunto = models.ForeignKey(
        ConjuntoInsumos,
        on_delete=models.PROTECT,
        related_name="franjas_utilizables",
    )
    salon = models.ForeignKey(Salon, on_delete=models.PROTECT)
    codigo_salon_copia = models.CharField(max_length=30)
    dia = models.PositiveSmallIntegerField()
    inicio = models.TimeField()
    fin = models.TimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conjunto", "salon", "dia", "inicio", "fin"],
                name="programacion_franja_unica",
            ),
            models.CheckConstraint(
                condition=models.Q(dia__gte=1, dia__lte=6),
                name="programacion_franja_dia_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(inicio__lt=models.F("fin")),
                name="programacion_franja_horas_validas",
            ),
        ]
class Oferta(models.Model):
    conjunto = models.ForeignKey(
        ConjuntoInsumos,
        on_delete=models.PROTECT,
        related_name="ofertas",
    )
    codigo = models.CharField(max_length=30)
    curso_propuesto = models.ForeignKey(
        "disponibilidad.CursoPropuesto",
        on_delete=models.PROTECT,
        related_name="ofertas_programacion",
    )
    grupo = models.ForeignKey(Grupo, on_delete=models.PROTECT)
    codigo_grupo_copia = models.CharField(max_length=30)
    grupo_copia = models.CharField(max_length=150)
    turno_ref = models.CharField(max_length=40, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conjunto", "codigo"],
                name="programacion_oferta_codigo_unico",
            ),
            models.UniqueConstraint(
                fields=["conjunto", "curso_propuesto", "grupo"],
                name="programacion_oferta_curso_grupo_unico",
            ),
        ]


class SesionRequerida(models.Model):
    oferta = models.ForeignKey(
        Oferta,
        on_delete=models.PROTECT,
        related_name="sesiones_requeridas",
    )
    numero = models.PositiveIntegerField()
    duracion_min = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["oferta", "numero"],
                name="programacion_sesion_numero_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(numero__gt=0, duracion_min__gt=0),
                name="programacion_sesion_valores_positivos",
            ),
        ]

class OpcionHabilitada(models.Model):
    oferta = models.ForeignKey(
        Oferta,
        on_delete=models.PROTECT,
        related_name="opciones_habilitadas",
    )
    opcion_semanal = models.ForeignKey(
        "disponibilidad.OpcionSemanal",
        on_delete=models.PROTECT,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["oferta", "opcion_semanal"],
                name="programacion_oferta_opcion_unica",
            ),
        ]


class CorrespondenciaSesion(models.Model):
    opcion_habilitada = models.ForeignKey(
        OpcionHabilitada,
        on_delete=models.PROTECT,
        related_name="correspondencias",
    )
    sesion = models.ForeignKey(
        SesionRequerida,
        on_delete=models.PROTECT,
    )
    bloque = models.ForeignKey(
        "disponibilidad.BloqueHorario",
        on_delete=models.PROTECT,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opcion_habilitada", "sesion"],
                name="programacion_correspondencia_sesion_unica",
            ),
            models.UniqueConstraint(
                fields=["opcion_habilitada", "bloque"],
                name="programacion_correspondencia_bloque_unico",
            ),
        ]
class EjecucionGeneracion(models.Model):
    class Estado(models.TextChoices):
        EN_COLA = "EN_COLA", "En cola"
        EJECUTANDO = "EJECUTANDO", "Ejecutando"
        FINALIZADA = "FINALIZADA", "Finalizada"
        FALLIDA = "FALLIDA", "Fallida"

    class Resultado(models.TextChoices):
        COMPLETO = "COMPLETO", "Completo"
        PARCIAL = "PARCIAL", "Parcial"
        SIN_RESULTADO = "SIN_RESULTADO", "Sin resultado"

    conjunto = models.ForeignKey(
        ConjuntoInsumos,
        on_delete=models.PROTECT,
        related_name="ejecuciones_generacion",
    )
    clave_solicitud = models.UUIDField(unique=True)
    solicitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.EN_COLA,
    )
    resultado = models.CharField(
        max_length=13, choices=Resultado.choices, null=True, blank=True,
    )
    condicion_termino = models.CharField(max_length=40, null=True, blank=True)
    limite_ms = models.PositiveIntegerField()
    inicio_en = models.DateTimeField(null=True, blank=True)
    fin_en = models.DateTimeField(null=True, blank=True)
    pulso_en = models.DateTimeField(null=True, blank=True)
    token_ejecucion = models.UUIDField(null=True, blank=True)
    parametros = models.JSONField(default=dict, blank=True)


class Propuesta(models.Model):
    ejecucion = models.OneToOneField(
        EjecucionGeneracion,
        on_delete=models.PROTECT,
        related_name="propuesta",
    )
    version_trabajo = models.ForeignKey(
        "VersionHorario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="propuestas_en_trabajo",
    )
    creada_en = models.DateTimeField(auto_now_add=True)


class VersionHorario(models.Model):
    class Estado(models.TextChoices):
        COMPLETA = "COMPLETA", "Completa"
        PARCIAL = "PARCIAL", "Parcial"

    propuesta = models.ForeignKey(
        Propuesta,
        on_delete=models.PROTECT,
        related_name="versiones",
    )
    numero = models.PositiveIntegerField()
    version_origen = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="versiones_derivadas",
    )
    estado = models.CharField(max_length=8, choices=Estado.choices)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["propuesta", "numero"],
                name="programacion_propuesta_version_unica",
            ),
        ]


class SeleccionOpcion(models.Model):
    version = models.ForeignKey(
        VersionHorario,
        on_delete=models.PROTECT,
        related_name="selecciones",
    )
    oferta = models.ForeignKey(Oferta, on_delete=models.PROTECT)
    opcion_habilitada = models.ForeignKey(
        OpcionHabilitada,
        on_delete=models.PROTECT,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "oferta"],
                name="programacion_version_oferta_unica",
            ),
        ]


class Asignacion(models.Model):
    seleccion = models.ForeignKey(
        SeleccionOpcion,
        on_delete=models.PROTECT,
        related_name="asignaciones",
    )
    correspondencia = models.ForeignKey(
        CorrespondenciaSesion,
        on_delete=models.PROTECT,
    )
    franja = models.ForeignKey(FranjaUtilizable, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["seleccion", "correspondencia"],
                name="programacion_asignacion_correspondencia_unica",
            ),
        ]

