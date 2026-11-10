from django.conf import settings
from django.db import models


class Periodo(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    denominacion = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)


class Docente(models.Model):
    codigo = models.CharField(max_length=30, unique=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    nombres = models.CharField(max_length=200)
    contacto = models.CharField(max_length=254)


class Asignatura(models.Model):
    codigo = models.CharField(max_length=30, unique=True)
    denominacion = models.CharField(max_length=200)
    activo = models.BooleanField(default=True)

class Recopilacion(models.Model):
    class Estado(models.TextChoices):
        PREPARACION = "PREPARACION", "En preparación"
        ABIERTA = "ABIERTA", "Abierta"
        CERRADA = "CERRADA", "Cerrada"

    periodo = models.OneToOneField(
        Periodo,
        on_delete=models.PROTECT,
        related_name="recopilacion",
    )
    estado = models.CharField(
        max_length=15,
        choices=Estado.choices,
        default=Estado.PREPARACION,
    )
    apertura_en = models.DateTimeField(null=True, blank=True)
    cierre_en = models.DateTimeField(null=True, blank=True)


class Convocado(models.Model):
    recopilacion = models.ForeignKey(
        Recopilacion,
        on_delete=models.PROTECT,
        related_name="convocados",
    )
    docente = models.ForeignKey(
        Docente,
        on_delete=models.PROTECT,
        related_name="convocatorias",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recopilacion", "docente"],
                name="disponibilidad_convocado_unico",
            ),
        ]

class Declaracion(models.Model):
    convocado = models.OneToOneField(
        Convocado,
        on_delete=models.PROTECT,
        related_name="declaracion",
    )
    creada_en = models.DateTimeField(auto_now_add=True)


class RevisionFicha(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        ENVIADA = "ENVIADA", "Enviada"

    declaracion = models.ForeignKey(
        Declaracion,
        on_delete=models.PROTECT,
        related_name="revisiones",
    )
    numero = models.PositiveIntegerField()
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    enviada_en = models.DateTimeField(null=True, blank=True)

    codigo_docente = models.CharField(max_length=30, blank=True)
    nombres = models.CharField(max_length=200, blank=True)
    contacto = models.CharField(max_length=254, blank=True)
    categoria = models.CharField(max_length=100, blank=True)
    dedicacion = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["declaracion", "numero"],
                name="disponibilidad_revision_numero_unico",
            ),
        ]

class CursoPropuesto(models.Model):
    revision = models.ForeignKey(
        RevisionFicha,
        on_delete=models.PROTECT,
        related_name="cursos_propuestos",
    )
    asignatura = models.ForeignKey(Asignatura, on_delete=models.PROTECT)
    prioridad = models.PositiveIntegerField()
    denominacion_copia = models.CharField(max_length=200)
    plan_ref = models.CharField(max_length=100, blank=True)
    ciclo_ref = models.CharField(max_length=30, blank=True)
    escuela_ref = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "asignatura"],
                name="disponibilidad_curso_unico",
            ),
            models.UniqueConstraint(
                fields=["revision", "prioridad"],
                name="disponibilidad_prioridad_unica",
            ),
        ]


class OpcionSemanal(models.Model):
    curso_propuesto = models.ForeignKey(
        CursoPropuesto,
        on_delete=models.PROTECT,
        related_name="opciones",
    )
    numero = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["curso_propuesto", "numero"],
                name="disponibilidad_opcion_numero_unico",
            ),
        ]


class BloqueHorario(models.Model):
    opcion = models.ForeignKey(
        OpcionSemanal,
        on_delete=models.PROTECT,
        related_name="bloques",
    )
    numero = models.PositiveIntegerField()
    dia = models.PositiveSmallIntegerField()
    inicio = models.TimeField()
    fin = models.TimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opcion", "numero"],
                name="disponibilidad_bloque_numero_unico",
            ),
            models.UniqueConstraint(
                fields=["opcion", "dia", "inicio", "fin"],
                name="disponibilidad_bloque_intervalo_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(dia__gte=1, dia__lte=6),
                name="disponibilidad_bloque_dia_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(inicio__lt=models.F("fin")),
                name="disponibilidad_bloque_horas_validas",
            ),
        ]

class CargaNoLectiva(models.Model):
    class Tipo(models.TextChoices):
        INVESTIGACION = "INVESTIGACION", "Investigación"
        EXTENSION = "EXTENSION", "Extensión"
        GESTION = "GESTION", "Gestión"

    revision = models.ForeignKey(
        RevisionFicha,
        on_delete=models.PROTECT,
        related_name="cargas_no_lectivas",
    )
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    actividad = models.TextField()
    horas = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(horas__gte=0),
                name="disponibilidad_carga_horas_no_negativas",
            ),
        ]

class Auditoria(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    fecha = models.DateTimeField(auto_now_add=True)
    operacion = models.CharField(max_length=50)
    periodo = models.ForeignKey(
        Periodo,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    objeto_tipo = models.CharField(max_length=50)
    objeto_id = models.PositiveBigIntegerField()
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["objeto_tipo", "objeto_id", "fecha"],
                name="disp_audit_objeto_fecha_idx",
            ),
        ]