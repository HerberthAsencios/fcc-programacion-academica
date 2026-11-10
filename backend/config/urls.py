"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


from disponibilidad.views import borrador_ficha, sesion, listar_asignaturas, cursos_borrador,carga_no_lectiva, envio_ficha, nueva_revision, seguimiento_recopilacion, cambiar_estado_recopilacion, exportar_disponibilidad 


from programacion.views import crear_conjunto_insumos, crear_oferta, evaluar_opciones_oferta, habilitar_opcion,registrar_franja, congelar_conjunto, solicitar_generacion, consultar_ejecucion, consultar_propuesta, ajustar_salon_propuesta, historial_propuestas


from disponibilidad.views import (
    borrador_ficha,
    cursos_borrador,
    listar_asignaturas,
    opciones_curso,
    sesion,
)

def estado_api(request):
    return JsonResponse({"estado": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/estado/", estado_api),
    path("api/disponibilidad/<int:recopilacion_id>/borrador/",borrador_ficha,),
    path("api/sesion/", sesion),
    path("api/disponibilidad/<int:recopilacion_id>/asignaturas/",listar_asignaturas,),
    path("api/disponibilidad/<int:recopilacion_id>/cursos/",cursos_borrador,),
    path("api/disponibilidad/<int:recopilacion_id>/cursos/<int:curso_id>/opciones/",
            opciones_curso,),
    path("api/disponibilidad/<int:recopilacion_id>/carga-no-lectiva/",
        carga_no_lectiva,),
    path(
        "api/disponibilidad/<int:recopilacion_id>/envio/",
        envio_ficha,
    ),
    path(
        "api/disponibilidad/<int:recopilacion_id>/nueva-revision/",
        nueva_revision,
    ),
    path(
        "api/disponibilidad/<int:recopilacion_id>/cursos/<int:curso_id>/opciones/<int:opcion_id>/",
        opciones_curso,
    ),
    path(
        "api/gestion/recopilaciones/<int:recopilacion_id>/seguimiento/",
        seguimiento_recopilacion,
    ),  
      path(
        "api/gestion/recopilaciones/<int:recopilacion_id>/estado/",
        cambiar_estado_recopilacion,
    ),

    path(
        "api/gestion/recopilaciones/<int:recopilacion_id>/disponibilidad.csv",
        exportar_disponibilidad,
    ),
    path(
        "api/programacion/recopilaciones/<int:recopilacion_id>/insumos/",
        crear_conjunto_insumos,
    ),
    path("api/programacion/insumos/<int:conjunto_id>/ofertas/", crear_oferta),    path(
        "api/programacion/ofertas/<int:oferta_id>/opciones/",
        evaluar_opciones_oferta,
    ),
    path(
        "api/programacion/ofertas/<int:oferta_id>/opciones/<int:opcion_id>/habilitar/",
        habilitar_opcion,
    ),
    path("api/programacion/insumos/<int:conjunto_id>/franjas/", registrar_franja),
    path("api/programacion/insumos/<int:conjunto_id>/congelar/", congelar_conjunto),
    path("api/programacion/ejecuciones/", solicitar_generacion),
    path("api/programacion/ejecuciones/<int:ejecucion_id>/", consultar_ejecucion),
    path("api/programacion/propuestas/<int:propuesta_id>/", consultar_propuesta),
    path("api/programacion/propuestas/<int:propuesta_id>/ajustes/salon/",     ajustar_salon_propuesta,),
    path("api/programacion/recopilaciones/<int:recopilacion_id>/propuestas/",historial_propuestas,),

]
