import logging
from time import sleep

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from programacion.ejecuciones import procesar_ejecucion, tomar_ejecucion


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Procesa solicitudes de generación de horarios."

    def add_arguments(self, parser):
        parser.add_argument(
            "--continuo",
            action="store_true",
            help="Espera y procesa las solicitudes que entren en cola.",
        )

    def handle(self, *args, **options):
        continuo = options["continuo"]

        while True:
            close_old_connections()
            try:
                ejecucion = tomar_ejecucion()
                if ejecucion is not None:
                    resultado = procesar_ejecucion(ejecucion)
                    self.stdout.write(
                        f"Ejecucion {resultado.pk}: "
                        f"{resultado.estado} {resultado.resultado}"
                    )
                    if not continuo:
                        return
                    continue

                if not continuo:
                    self.stdout.write("No hay ejecuciones en cola.")
                    return
            except Exception:
                if not continuo:
                    raise
                logger.exception("Error al procesar la cola de horarios.")
            finally:
                close_old_connections()

            sleep(2)