from django.contrib import admin

from .models import Asignatura, Convocado, Docente, Periodo, Recopilacion


@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "denominacion", "activo")
    search_fields = ("codigo", "denominacion")

    def get_readonly_fields(self, request, obj=None):
        return ("codigo",) if obj else ()


@admin.register(Docente)
class DocenteAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombres", "contacto", "usuario")
    search_fields = ("codigo", "nombres", "contacto")


@admin.register(Asignatura)
class AsignaturaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "denominacion", "activo")
    search_fields = ("codigo", "denominacion")


@admin.register(Recopilacion)
class RecopilacionAdmin(admin.ModelAdmin):
    list_display = ("periodo", "estado", "apertura_en", "cierre_en")

    def get_readonly_fields(self, request, obj=None):
        campos = ("estado", "apertura_en", "cierre_en")
        return (*campos, "periodo") if obj else campos


@admin.register(Convocado)
class ConvocadoAdmin(admin.ModelAdmin):
    list_display = ("recopilacion", "docente", "activo")
    list_filter = ("recopilacion", "activo")
    search_fields = ("docente__codigo", "docente__nombres")

    def get_readonly_fields(self, request, obj=None):
        return ("recopilacion", "docente") if obj else ()