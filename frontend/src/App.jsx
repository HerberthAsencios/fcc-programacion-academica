import { useEffect, useState } from 'react'

const campos = [
  { nombre: 'contacto', etiqueta: 'Contacto', limite: 254 },
  { nombre: 'categoria', etiqueta: 'Categoría', limite: 100 },
  { nombre: 'dedicacion', etiqueta: 'Dedicación', limite: 100 },
]

function datosGenerales(borrador) {
  return Object.fromEntries(
    campos.map(({ nombre }) => [nombre, borrador?.[nombre] ?? '']),
  )
}

async function solicitar(ruta, opciones) {
  const respuesta = await fetch(ruta, opciones)
  const datos = await respuesta.json().catch(() => null)

  if (!respuesta.ok || datos === null) {
    throw new Error(datos?.error ?? `Error en la solicitud (${respuesta.status}).`)
  }

  return datos
}

function enviarJson(ruta, method, csrfToken, datos) {
  return solicitar(ruta, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: JSON.stringify(datos),
  })
}
const diasSemana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']

function nuevoBloque() {
  return { clave: crypto.randomUUID(), dia: '', inicio: '', fin: '' }
}

function OpcionesCurso({ convocatoria, curso, csrfToken }) {
  const [opciones, setOpciones] = useState(null)
  const [bloques, setBloques] = useState(() => [nuevoBloque()])
  const [mensaje, setMensaje] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [opcionEnEdicion, setOpcionEnEdicion] = useState(null)

  const ruta = `/api/disponibilidad/${convocatoria.id}/cursos/${curso.id}/opciones/`
  const abierta = convocatoria.estado === 'ABIERTA'

  useEffect(() => {
    const control = new AbortController()

    solicitar(ruta, { signal: control.signal })
      .then(({ opciones }) => setOpciones(opciones))
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })

    return () => control.abort()
  }, [ruta])

  function actualizarBloque(clave, campo, valor) {
    setBloques((actuales) =>
      actuales.map((bloque) =>
        bloque.clave === clave ? { ...bloque, [campo]: valor } : bloque,
      ),
    )
  }
  function editarOpcion(opcion) {
    setOpcionEnEdicion(opcion)
    setBloques(opcion.bloques.map((bloque) => ({
      ...nuevoBloque(),
      ...bloque,
      dia: String(bloque.dia),
    })))
    setMensaje('')
  }

  function cancelarEdicion() {
    setOpcionEnEdicion(null)
    setBloques([nuevoBloque()])
    setMensaje('')
  }

    async function guardarOpcion(evento) {
    evento.preventDefault()
    setGuardando(true)
    setMensaje('')

    const editando = opcionEnEdicion !== null
    const destino = editando ? `${ruta}${opcionEnEdicion.id}/` : ruta

    try {
      const { opcion } = await enviarJson(
        destino,
        editando ? 'PUT' : 'POST',
        csrfToken,
        {
          bloques: bloques.map(({ dia, inicio, fin }) => ({
            dia: Number(dia),
            inicio,
            fin,
          })),
        },
      )

      setOpciones((actuales) =>
        editando
          ? actuales.map((actual) => actual.id === opcion.id ? opcion : actual)
          : [...actuales, opcion],
      )
      setOpcionEnEdicion(null)
      setBloques([nuevoBloque()])
      setMensaje(`Opción ${opcion.numero} ${editando ? 'actualizada' : 'guardada'}.`)
    } catch (error) {
      setMensaje(error.message)
    } finally {
      setGuardando(false)
    }
  }

  if (opciones === null) {
    return <p role="status">{mensaje || 'Cargando opciones…'}</p>
  }

  return (
    <section>
      <h3>Opciones semanales</h3>

      {opciones.length === 0 && <p>Aún no hay opciones para este curso.</p>}

      {opciones.map((opcion) => (
        <div key={opcion.id}>
          <strong>Opción {opcion.numero}</strong>
                    {abierta && (
            <button
              type="button"
              onClick={() => editarOpcion(opcion)}
              disabled={guardando || opcionEnEdicion !== null}
            >
              Editar opción
            </button>
          )}
          <ul>
            {opcion.bloques.map(({ dia, inicio, fin }) => (
              <li key={`${dia}-${inicio}-${fin}`}>
                {diasSemana[dia - 1]} · {inicio} a {fin}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {abierta && (
        <form onSubmit={guardarOpcion}>
          <fieldset disabled={guardando}>
            <legend>
              {opcionEnEdicion ? `Editar opción ${opcionEnEdicion.numero}` : 'Nueva opción semanal'}
            </legend>

            {bloques.map((bloque, indice) => (
              <fieldset key={bloque.clave}>
                <legend>Bloque {indice + 1}</legend>
                <label>
                  Día{' '}
                  <select
                    required
                    value={bloque.dia}
                    onChange={(e) => actualizarBloque(bloque.clave, 'dia', e.target.value)}
                  >
                    <option value="">Selecciona un día</option>
                    {diasSemana.map((dia, posicion) => (
                      <option key={dia} value={posicion + 1}>{dia}</option>
                    ))}
                  </select>
                </label>{' '}
                <label>
                  Inicio{' '}
                  <input
                    type="time"
                    required
                    value={bloque.inicio}
                    onChange={(e) => actualizarBloque(bloque.clave, 'inicio', e.target.value)}
                  />
                </label>{' '}
                <label>
                  Fin{' '}
                  <input
                    type="time"
                    required
                    value={bloque.fin}
                    onChange={(e) => actualizarBloque(bloque.clave, 'fin', e.target.value)}
                  />
                </label>{' '}
                {bloques.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setBloques((actuales) =>
                      actuales.filter(({ clave }) => clave !== bloque.clave),
                    )}
                  >
                    Quitar bloque
                  </button>
                )}
              </fieldset>
            ))}

            <button type="button" onClick={() => setBloques([...bloques, nuevoBloque()])}>
              Agregar bloque
            </button>{' '}

                        {opcionEnEdicion && (
              <button type="button" onClick={cancelarEdicion}>
                Cancelar edición
              </button>
            )}
            <button type="submit">{guardando ? 'Guardando…' : 'Guardar opción'}</button>
          </fieldset>
        </form>
      )}

      <p role="status">{mensaje}</p>
    </section>
  )
}

function CursosBorrador({ convocatoria, csrfToken }) {
  const [asignaturas, setAsignaturas] = useState(null)
  const [cursos, setCursos] = useState([])
  const [asignaturaId, setAsignaturaId] = useState('')
  const [prioridad, setPrioridad] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [guardando, setGuardando] = useState(false)

  const rutaBase = `/api/disponibilidad/${convocatoria.id}`
  const abierta = convocatoria.estado === 'ABIERTA'

  useEffect(() => {
    const control = new AbortController()
    const opciones = { signal: control.signal }

    Promise.all([
      solicitar(`${rutaBase}/asignaturas/`, opciones),
      solicitar(`${rutaBase}/cursos/`, opciones),
    ])
      .then(([catalogo, borrador]) => {
        setAsignaturas(catalogo.asignaturas)
        setCursos(borrador.cursos)
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })

    return () => control.abort()
  }, [rutaBase])

  async function agregarCurso(evento) {
    evento.preventDefault()
    setGuardando(true)
    setMensaje('')

    try {
      const { curso } = await enviarJson(`${rutaBase}/cursos/`, 'POST', csrfToken, {
        asignatura_id: Number(asignaturaId),
        prioridad: Number(prioridad),
      })
      setCursos((actuales) =>
        [...actuales, curso].sort((a, b) => a.prioridad - b.prioridad),
      )
      setAsignaturaId('')
      setPrioridad('')
      setMensaje('Curso agregado al borrador.')
    } catch (error) {
      setMensaje(error.message)
    } finally {
      setGuardando(false)
    }
  }

  if (asignaturas === null) {
    return <p role="status">{mensaje || 'Cargando cursos…'}</p>
  }

  const disponibles = asignaturas.filter(
    ({ id }) => !cursos.some(({ asignatura_id }) => asignatura_id === id),
  )

  return (
    <section>
      <h2>Cursos propuestos</h2>

      {cursos.length === 0 ? (
        <p>Aún no has agregado cursos.</p>
      ) : (
        <ul>
         {cursos.map((curso) => (
  <li key={curso.id}>
    <strong>Prioridad {curso.prioridad} · {curso.denominacion_copia}</strong>
    <OpcionesCurso
      convocatoria={convocatoria}
      curso={curso}
      csrfToken={csrfToken}
    />
  </li>
))}
        </ul>
      )}

      {abierta && disponibles.length > 0 && (
        <form onSubmit={agregarCurso}>
          <fieldset disabled={guardando}>
            <p>
              <label>
                Asignatura{' '}
                <select
                  required
                  value={asignaturaId}
                  onChange={(evento) => setAsignaturaId(evento.target.value)}
                >
                  <option value="">Selecciona una asignatura</option>
                  {disponibles.map(({ id, codigo, denominacion }) => (
                    <option key={id} value={id}>{codigo} · {denominacion}</option>
                  ))}
                </select>
              </label>
            </p>
            <p>
              <label>
                Prioridad{' '}
                <input
                  type="number"
                  min="1"
                  step="1"
                  required
                  value={prioridad}
                  onChange={(evento) => setPrioridad(evento.target.value)}
                />
              </label>
            </p>
            <button type="submit">{guardando ? 'Agregando…' : 'Agregar curso'}</button>
          </fieldset>
        </form>
      )}

      <p role="status">{mensaje}</p>
    </section>
  )
}
const tiposCarga = {
  INVESTIGACION: 'Investigación',
  EXTENSION: 'Extensión',
  GESTION: 'Gestión',
}

function CargaNoLectiva({ convocatoria, csrfToken }) {
  const [actividades, setActividades] = useState(null)
  const [mensaje, setMensaje] = useState('')
  const [guardando, setGuardando] = useState(false)
  const ruta = `/api/disponibilidad/${convocatoria.id}/carga-no-lectiva/`
  const abierta = convocatoria.estado === 'ABIERTA'

  useEffect(() => {
    const control = new AbortController()

    solicitar(ruta, { signal: control.signal })
      .then(({ actividades }) => setActividades(actividades))
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })

    return () => control.abort()
  }, [ruta])

  async function agregarActividad(evento) {
    evento.preventDefault()
    const formulario = evento.currentTarget
    const datos = Object.fromEntries(new FormData(formulario))
    setGuardando(true)
    setMensaje('')

    try {
      const { actividad } = await enviarJson(ruta, 'POST', csrfToken, datos)
      setActividades((actuales) => [...actuales, actividad])
      formulario.reset()
      setMensaje('Actividad agregada al borrador.')
    } catch (error) {
      setMensaje(error.message)
    } finally {
      setGuardando(false)
    }
  }

  if (actividades === null) {
    return <p role="status">{mensaje || 'Cargando carga no lectiva…'}</p>
  }

  return (
    <section>
      <h2>Carga no lectiva</h2>

      {actividades.length === 0 ? (
        <p>Aún no has registrado actividades.</p>
      ) : (
        <ul>
          {actividades.map(({ id, tipo, actividad, horas }) => (
            <li key={id}>{tiposCarga[tipo]} · {actividad} · {horas} h</li>
          ))}
        </ul>
      )}

      {abierta && (
        <form onSubmit={agregarActividad}>
          <fieldset disabled={guardando}>
            <legend>Nueva actividad</legend>

            <p>
              <label>
                Tipo{' '}
                <select name="tipo" defaultValue="" required>
                  <option value="">Selecciona un tipo</option>
                  {Object.entries(tiposCarga).map(([valor, etiqueta]) => (
                    <option key={valor} value={valor}>{etiqueta}</option>
                  ))}
                </select>
              </label>
            </p>

            <p>
              <label>
                Descripción <textarea name="actividad" required />
              </label>
            </p>

            <p>
              <label>
                Horas{' '}
                <input name="horas" type="number" min="0" max="9999.99" step="0.01" required />
              </label>
            </p>

            <button type="submit">
              {guardando ? 'Agregando…' : 'Agregar actividad'}
            </button>
          </fieldset>
        </form>
      )}

      <p role="status">{mensaje}</p>
    </section>
  )
}

function Ficha({ convocatoria, csrfToken }) {
  const [datos, setDatos] = useState(null)
  const [identidad, setIdentidad] = useState(null)
  const [enviada, setEnviada] = useState(null)
  const [mensaje, setMensaje] = useState('')
  const [mensajeEnvio, setMensajeEnvio] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [preparando, setPreparando] = useState(false)

  const rutaBase = `/api/disponibilidad/${convocatoria.id}`
  const rutaBorrador = `${rutaBase}/borrador/`
  const rutaEnvio = `${rutaBase}/envio/`
  const abierta = convocatoria.estado === 'ABIERTA'

  useEffect(() => {
    const control = new AbortController()
    const opciones = { signal: control.signal }

    Promise.all([
      solicitar(rutaBorrador, opciones),
      solicitar(rutaEnvio, opciones),
    ])
      .then(([ficha, envio]) => {
        setDatos(datosGenerales(ficha.borrador))
        setIdentidad(ficha.borrador)
        setEnviada(envio.enviada)
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })

    return () => control.abort()
  }, [rutaBorrador, rutaEnvio])

  async function guardar(evento) {
    evento.preventDefault()
    setGuardando(true)
    setMensaje('')
    setMensajeEnvio('')

    try {
      const { borrador } = await enviarJson(rutaBorrador, 'PUT', csrfToken, datos)
      setDatos(datosGenerales(borrador))
      setIdentidad(borrador)
      setMensaje(`Borrador guardado. Revisión ${borrador.numero}.`)
    } catch (error) {
      setMensaje(error.message)
    } finally {
      setGuardando(false)
    }
  }

  async function enviarFicha() {
    setEnviando(true)
    setMensajeEnvio('')

    try {
      const respuesta = await enviarJson(rutaEnvio, 'POST', csrfToken, {
        numero: identidad.numero,
      })
      setEnviada(respuesta.enviada)
      setIdentidad(null)
    } catch (error) {
      setMensajeEnvio(error.message)
    } finally {
      setEnviando(false)
    }
  }
    async function prepararRevision() {
    setPreparando(true)
    setMensajeEnvio('')

    try {
      const { borrador } = await enviarJson(
        `${rutaBase}/nueva-revision/`,
        'POST',
        csrfToken,
        {},
      )
      setDatos(datosGenerales(borrador))
      setIdentidad(borrador)
      setMensaje(`Borrador de la revisión ${borrador.numero} listo para editar.`)
    } catch (error) {
      setMensajeEnvio(error.message)
    } finally {
      setPreparando(false)
    }
  }

  if (datos === null) return <p role="status">{mensaje || 'Cargando ficha…'}</p>

  const hayCambiosSinGuardar = identidad !== null && campos.some(
    ({ nombre }) => datos[nombre] !== identidad[nombre],
  )

  return (
    <>
      {enviada && (
        <section>
          <h2>Ficha recibida</h2>
          <p>
            Revisión {enviada.numero} ·{' '}
            {new Date(enviada.enviada_en).toLocaleString('es-PE')}
          </p>
                {abierta && !identidad && (
            <>
              <button type="button" onClick={prepararRevision} disabled={preparando}>
                {preparando ? 'Preparando…' : 'Preparar nueva revisión'}
              </button>
              <p role="status">{mensajeEnvio}</p>
            </>
          )}
        </section>
      )}

      {(identidad || !enviada) && (
        <form onSubmit={guardar}>
          <h2>Datos generales</h2>
          {identidad && <p>{identidad.nombres} · {identidad.codigo_docente}</p>}
          {!abierta && <p>La recopilación no está abierta para edición.</p>}

          <fieldset disabled={!abierta || guardando || enviando}>
            {campos.map(({ nombre, etiqueta, limite }) => (
              <p key={nombre}>
                <label>
                  {etiqueta}{' '}
                  <input
                    value={datos[nombre]}
                    maxLength={limite}
                    onChange={(evento) =>
                      setDatos({ ...datos, [nombre]: evento.target.value })
                    }
                  />
                </label>
              </p>
            ))}
            <button type="submit">
              {guardando ? 'Guardando…' : 'Guardar borrador'}
            </button>
          </fieldset>

          <p role="status">{mensaje}</p>
        </form>
      )}

      {identidad && (
        <>
          <CursosBorrador convocatoria={convocatoria} csrfToken={csrfToken} />
          <CargaNoLectiva convocatoria={convocatoria} csrfToken={csrfToken} />

          {abierta && (
            <section>
              <h2>Enviar ficha</h2>
              {hayCambiosSinGuardar && <p>Guarda los cambios de datos generales antes de enviar.</p>}
              <button
                type="button"
                onClick={enviarFicha}
                disabled={enviando || guardando || hayCambiosSinGuardar}
              >
                {enviando ? 'Enviando…' : 'Enviar ficha'}
              </button>
              <p role="status">{mensajeEnvio}</p>
            </section>
          )}
        </>
      )}

      {!identidad && !enviada && (
        <p>Guarda los datos generales para agregar cursos y actividades.</p>
      )}
    </>
  )
}

function DetallePropuesta({ propuestaId, csrfToken }) {
  const [propuesta, setPropuesta] = useState(null)
  const [mensaje, setMensaje] = useState('')
  const [guardando, setGuardando] = useState(false)
  const ruta = `/api/programacion/propuestas/${propuestaId}/`
  const versionElegida =
    propuesta && !propuesta.es_version_trabajo ? String(propuesta.version) : ''

  useEffect(() => {
    const control = new AbortController()

    solicitar(ruta, { signal: control.signal, cache: 'no-store' })
      .then(setPropuesta)
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })

    return () => control.abort()
  }, [ruta])

  async function actualizarHorario(numero = versionElegida) {
    const rutaConsulta = numero ? `${ruta}?version=${numero}` : ruta
    const actual = await solicitar(rutaConsulta, { cache: 'no-store' })
    setPropuesta(actual)
  }

  async function verVersion(numero) {
    setGuardando(true)
    setMensaje('')

    try {
      await actualizarHorario(numero)
    } catch (error) {
      setMensaje(error.message)
    } finally {
      setGuardando(false)
    }
  }

  async function cambiarSalon(evento, asignacionId) {
    evento.preventDefault()
    if (guardando) return

    const formulario = new FormData(evento.currentTarget)
    const franjaId = Number(formulario.get('franja_id'))
    if (!franjaId) return

    setGuardando(true)
    setMensaje('')

    let ajuste
    try {
      ajuste = await enviarJson(`${ruta}ajustes/salon/`, 'POST', csrfToken, {
        version_base_id: propuesta.version_id,
        asignacion_id: asignacionId,
        franja_id: franjaId,
      })
      await actualizarHorario()
      setMensaje(`Cambio guardado en la versión ${ajuste.version}.`)
    } catch (error) {
      setMensaje(ajuste
        ? `La versión ${ajuste.version} se guardó. Pulsa Actualizar horario para verla.`
        : error.message)
    } finally {
      setGuardando(false)
    }
  }

  if (!propuesta) return <p role="status">{mensaje || 'Cargando horario…'}</p>

  return (
    <section>
      <h4>Horario propuesto · Versión {propuesta.version}</h4>
      <label>
        Versión del horario{' '}
        <select
          value={versionElegida}
          disabled={guardando}
          onChange={(evento) => verVersion(evento.target.value)}
        >
          <option value="">Versión de trabajo</option>
          {propuesta.versiones?.map(({ numero }) => (
            <option key={numero} value={numero}>
              Versión {numero}
            </option>
          ))}
        </select>
      </label>{' '}
      <button
        type="button"
        disabled={guardando}
        onClick={() => verVersion(versionElegida)}
      >
        Actualizar horario
      </button>
      {!propuesta.es_version_trabajo && (
        <p>Versión histórica · Solo lectura</p>
      )}
      
      <p role="status">{mensaje}</p>

      <table>
        <thead>
          <tr>
            <th scope="col">Asignatura</th>
            <th scope="col">Docente</th>
            <th scope="col">Grupo</th>
            <th scope="col">Día</th>
            <th scope="col">Horario</th>
            <th scope="col">Salón</th>
            {propuesta.puede_ajustar && <th scope="col">Ajuste</th>}
          </tr>
        </thead>
        <tbody>
          {propuesta.sesiones.map((sesion) => (
            <tr key={sesion.id}>
              <td>{sesion.asignatura}</td>
              <td>{sesion.docente}</td>
              <td>{sesion.grupo}</td>
              <td>{diasSemana[sesion.dia - 1]}</td>
              <td>{sesion.inicio} a {sesion.fin}</td>
              <td>{sesion.salon}</td>
              {propuesta.puede_ajustar && (
                <td>
                  {sesion.salones_alternativos.length === 0 ? (
                    'Sin otro salón disponible'
                  ) : (
                    <form onSubmit={(evento) => cambiarSalon(evento, sesion.id)}>
                      <label>
                        Nuevo salón{' '}
                        <select name="franja_id" defaultValue="" required disabled={guardando}>
                          <option value="">Selecciona un salón</option>
                          {sesion.salones_alternativos.map(({ franja_id, salon }) => (
                            <option key={franja_id} value={franja_id}>{salon}</option>
                          ))}
                        </select>
                      </label>{' '}
                      <button type="submit" disabled={guardando}>Cambiar salón</button>
                    </form>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {propuesta.pendientes.length > 0 && (
        <p>Ofertas pendientes en esta versión: {propuesta.pendientes.join(', ')}</p>
      )}
    </section>
  )
}

function GeneracionHorario({ conjuntos, csrfToken, ultimaEjecucionId, recopilacionId }) {
  const [seleccion, setSeleccion] = useState('')
  const [ejecucion, setEjecucion] = useState(null)
  const [clave, setClave] = useState('')
  const [solicitando, setSolicitando] = useState(false)
  const [mensaje, setMensaje] = useState('')
  const [restaurando, setRestaurando] = useState(Boolean(ultimaEjecucionId))
  const claveHistorial = `fcc.propuestaHistorial.${recopilacionId}`
  const [historial, setHistorial] = useState(null)
  const [errorHistorial, setErrorHistorial] = useState('')
  const [propuestaElegida, setPropuestaElegida] = useState(
    () => sessionStorage.getItem(claveHistorial) ?? '',)
  const conjuntoId = seleccion || String(conjuntos[0]?.id ?? '')
  const ejecucionId = ejecucion?.id
  const enProceso =
    ejecucion?.estado === 'EN_COLA' || ejecucion?.estado === 'EJECUTANDO'
  
  
    useEffect(() => {
    if (!ultimaEjecucionId) return

    const control = new AbortController()

    solicitar(`/api/programacion/ejecuciones/${ultimaEjecucionId}/`, {
      signal: control.signal,
      cache: 'no-store',
    })
      .then((actual) => {
        setEjecucion(actual)
        setSeleccion(String(actual.conjunto_id))
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })
      .finally(() => {
        if (!control.signal.aborted) setRestaurando(false)
      })

    return () => control.abort()
  }, [ultimaEjecucionId])

  useEffect(() => {
    if (!ejecucionId || !enProceso) return

    const control = new AbortController()
    let temporizador

    async function consultar() {
      try {
        const actual = await solicitar(`/api/programacion/ejecuciones/${ejecucionId}/`, {
          signal: control.signal,
          cache: 'no-store',
        })
        setEjecucion(actual)
        setMensaje('')
      } catch (error) {
        if (error.name !== 'AbortError') setMensaje(error.message)
      } finally {
        if (!control.signal.aborted) {
          temporizador = setTimeout(consultar, 1500)
        }
      }
    }

    temporizador = setTimeout(consultar, 1500)

    return () => {
      control.abort()
      clearTimeout(temporizador)
    }
  }, [ejecucionId, enProceso])

  const propuestaRecienteId = ejecucion?.propuesta_id

  useEffect(() => {
    const control = new AbortController()

    solicitar(`/api/programacion/recopilaciones/${recopilacionId}/propuestas/`, {
      signal: control.signal,
      cache: 'no-store',
    })
      .then(({ propuestas }) => {
        setHistorial(propuestas)
        setErrorHistorial('')
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setErrorHistorial(error.message)
      })

    return () => control.abort()
  }, [recopilacionId, propuestaRecienteId])

  const propuestaDelHistorial = historial?.find(
    ({ id }) => String(id) === propuestaElegida,
  )
  const propuestaVisibleId = propuestaElegida && historial === null && !errorHistorial
    ? null
    : (propuestaDelHistorial?.id ?? propuestaRecienteId)

  function seleccionarPropuesta(id) {
    setPropuestaElegida(id)
    if (id) {
      sessionStorage.setItem(claveHistorial, id)
    } else {
      sessionStorage.removeItem(claveHistorial)
    }
  }
  async function generar(evento) {
    evento.preventDefault()
    if (!conjuntoId || solicitando || enProceso) return

    const claveSolicitud = clave || crypto.randomUUID()
    setClave(claveSolicitud)
    setSolicitando(true)
    setMensaje('')

    try {
      const respuesta = await enviarJson(
        '/api/programacion/ejecuciones/',
        'POST',
        csrfToken,
        {
          conjunto_id: Number(conjuntoId),
          clave_solicitud: claveSolicitud,
        },
      )
      setEjecucion(respuesta)
      seleccionarPropuesta('')
      setClave('')
    } catch (error) {
      setMensaje(error.message)
    } finally {
      setSolicitando(false)
    }
  }

  return (
    <section>
      <h3>Generación de horario</h3>

      {conjuntos.length === 0 ? (
        <p>Esta recopilación aún no tiene conjuntos congelados.</p>
      ) : (
        <form onSubmit={generar}>
          <fieldset disabled={restaurando || solicitando || enProceso}>
            <label>
              Conjunto de insumos{' '}
              <select
                value={conjuntoId}
                onChange={(evento) => {
                  setSeleccion(evento.target.value)
                  setClave('')
                  setEjecucion(null)
                  setMensaje('')
                }}
              >
                {conjuntos.map(({ id, numero }) => (
                  <option key={id} value={id}>Conjunto {numero}</option>
                ))}
              </select>
            </label>{' '}
            <button type="submit">
              {solicitando ? 'Solicitando…' : 'Generar horario'}
            </button>
          </fieldset>
        </form>
      )}

      {ejecucion && (
        <div role="status">
          <p>
            Ejecución {ejecucion.id} · <strong>{ejecucion.estado}</strong>
            {ejecucion.resultado && ` · ${ejecucion.resultado}`}
          </p>
          {ejecucion.propuesta_id && <p>Propuesta guardada: {ejecucion.propuesta_id}</p>}
          {ejecucion.pendientes.length > 0 && (
            <p>Ofertas pendientes: {ejecucion.pendientes.join(', ')}</p>
          )}
        </div>
       )}
            <h4>Historial de propuestas</h4>
      {errorHistorial && <p role="status">{errorHistorial}</p>}
      {historial?.length === 0 && <p>Aún no tienes propuestas guardadas.</p>}

      {historial?.length > 0 && (
        <label>
          Abrir propuesta{' '}
          <select
            value={propuestaDelHistorial ? propuestaElegida : ''}
            onChange={(evento) => seleccionarPropuesta(evento.target.value)}
          >
            <option value="">Propuesta de la última ejecución</option>
            {historial.map(({ id, conjunto_numero, creada_en }) => (
              <option key={id} value={id}>
                Propuesta {id} · Conjunto {conjunto_numero} ·{' '}
                {new Date(creada_en).toLocaleString('es-PE')}
              </option>
            ))}
          </select>
        </label>
      )}

      {propuestaVisibleId && (
        <DetallePropuesta
          key={propuestaVisibleId}
          propuestaId={propuestaVisibleId}
          csrfToken={csrfToken}
        />
      )}
      


      {mensaje && <p role="status">{mensaje}</p>}
    </section>
  )
}

function SeguimientoGestion({ recopilaciones, puedeCambiarEstado, csrfToken }) {
  const [seleccion, setSeleccion] = useState(
    () => sessionStorage.getItem('fcc.recopilacionSeguimiento') ?? '',
  )
  const [datos, setDatos] = useState(null)
  const [mensaje, setMensaje] = useState('')
  const recopilacionId = String(
    (recopilaciones.find(({ id }) => String(id) === seleccion) ?? recopilaciones[0])?.id ?? '',
  )
  const [cambiando, setCambiando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [mensajeEstado, setMensajeEstado] = useState('')

  useEffect(() => {
    if (!recopilacionId) return

    const control = new AbortController()
    solicitar(`/api/gestion/recopilaciones/${recopilacionId}/seguimiento/`, {
      signal: control.signal,
      cache:'no-store'
    })
      .then(setDatos)
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })

   const accionActual = {
    PREPARACION: { codigo: 'ABRIR', texto: 'Abrir recopilación' },
    ABIERTA: { codigo: 'CERRAR', texto: 'Cerrar recopilación' },
    CERRADA: { codigo: 'REABRIR', texto: 'Reabrir recopilación' },
   }[datos?.estado]

   async function cambiarEstado(evento) {
    evento.preventDefault()
    setCambiando(true)
    setMensajeEstado('')

    try {
      const respuesta = await enviarJson(
        `/api/gestion/recopilaciones/${recopilacionId}/estado/`,
        'POST',
        csrfToken,
        { accion: accionActual.codigo, motivo: motivo.trim() },
      )
      setDatos((actuales) => ({ ...actuales, estado: respuesta.estado }))
      setMotivo('')
      setMensajeEstado('Estado actualizado.')
    } catch (error) {
      setMensajeEstado(error.message)
    } finally {
      setCambiando(false)
    }
   }
  
    return () => control.abort()
  }, [recopilacionId])

    function cambiarRecopilacion(evento) {
    setDatos(null)
    setMensaje('')
    setMotivo('')
    setMensajeEstado('')
    setSeleccion(evento.target.value)
    sessionStorage.setItem('fcc.recopilacionSeguimiento', evento.target.value)
  }

  const accionActual = {
    PREPARACION: { codigo: 'ABRIR', texto: 'Abrir recopilación' },
    ABIERTA: { codigo: 'CERRAR', texto: 'Cerrar recopilación' },
    CERRADA: { codigo: 'REABRIR', texto: 'Reabrir recopilación' },
  }[datos?.estado]

  async function cambiarEstado(evento) {
    evento.preventDefault()
    if (!accionActual || cambiando) return

    setCambiando(true)
    setMensajeEstado('')

    try {
      const respuesta = await enviarJson(
        `/api/gestion/recopilaciones/${recopilacionId}/estado/`,
        'POST',
        csrfToken,
        { accion: accionActual.codigo, motivo: motivo.trim() },
      )
      setDatos((actuales) => ({ ...actuales, estado: respuesta.estado }))
      setMotivo('')
      setMensajeEstado('Estado actualizado.')
    } catch (error) {
      setMensajeEstado(error.message)
    } finally {
      setCambiando(false)
    }
  }

  return (
    <section>
      <h2>Seguimiento académico</h2>

      {recopilaciones.length === 0 ? (
        <p>Aún no hay recopilaciones registradas.</p>
      ) : (
        <>
          <label>
            Recopilación{' '}
            <select value={recopilacionId} onChange={cambiarRecopilacion} disabled={cambiando}>
              {recopilaciones.map(({ id, periodo }) => (
                <option key={id} value={id}>{periodo}</option>
              ))}
            </select>
          </label>

          {datos === null ? (
            <p role="status">{mensaje || 'Cargando seguimiento…'}</p>
          ) : (
            <>
              <p>
                {datos.total} convocados · {datos.recibidas} recibidas ·{' '}
                {datos.pendientes} pendientes
              </p>
                            <p>Estado de la recopilación: <strong>{datos.estado}</strong></p>

              {puedeCambiarEstado && accionActual && (
                <form onSubmit={cambiarEstado}>
                  <fieldset disabled={cambiando}>
                    {accionActual.codigo === 'REABRIR' && (
                      <p>
                        <label>
                          Motivo de reapertura{' '}
                          <textarea
                            required
                            value={motivo}
                            onChange={(evento) => setMotivo(evento.target.value)}
                          />
                        </label>
                      </p>
                    )}
                    <button
                      type="submit"
                      disabled={accionActual.codigo === 'REABRIR' && !motivo.trim()}
                    >
                      {cambiando ? 'Guardando…' : accionActual.texto}
                    </button>
                  </fieldset>
                  <p role="status">{mensajeEstado}</p>
                </form>
              )}

              <p>
                <a href={`/api/gestion/recopilaciones/${recopilacionId}/disponibilidad.csv`}>
                  Exportar disponibilidad (CSV)
                </a>
              </p>


              <table>
                <caption>Estado de las fichas docentes</caption>
                <thead>
                  <tr>
                    <th scope="col">Código</th>
                    <th scope="col">Docente</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Revisión enviada</th>
                    <th scope="col">Fecha de envío</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.docentes.map((docente) => (
                    <tr key={docente.codigo}>
                      <td>{docente.codigo}</td>
                      <td>{docente.nombres}</td>
                      <td>{docente.estado === 'RECIBIDA' ? 'Recibida' : 'Pendiente'}</td>
                      <td>{docente.revision_enviada ?? '—'}</td>
                      <td>
                        {docente.fecha_envio
                          ? new Date(docente.fecha_envio).toLocaleString('es-PE')
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
                {datos.puede_generar && (
               <GeneracionHorario
                  key={recopilacionId}
                  recopilacionId={recopilacionId}
                  conjuntos={datos.conjuntos_congelados}
                  csrfToken={csrfToken}
                  ultimaEjecucionId={datos.ultima_ejecucion_id}
                />
              )}
            </>
          )}
        </>
      )}
    </section>
  )
}

export default function App() {
  const [sesion, setSesion] = useState(null)
  const [seleccion, setSeleccion] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [ingresando, setIngresando] = useState(false)

  useEffect(() => {
    const control = new AbortController()

    solicitar('/api/sesion/', { signal: control.signal })
      .then(setSesion)
      .catch((error) => {
        if (error.name !== 'AbortError') setMensaje(error.message)
      })

    return () => control.abort()
  }, [])

  async function ingresar(evento) {
    evento.preventDefault()
    const formulario = new FormData(evento.currentTarget)
    setIngresando(true)
    setMensaje('')

    try {
      const resultado = await enviarJson('/api/sesion/', 'POST', sesion.csrfToken, {
        usuario: formulario.get('usuario'),
        clave: formulario.get('clave'),
      })
      setSesion(resultado)
    } catch (error) {
      setMensaje(error.message)
    } finally {
      setIngresando(false)
    }
  }
  const puedeGestionar = Array.isArray(sesion?.recopilaciones_gestion)
  const convocatorias = sesion?.convocatorias ?? []
  const convocatoria =
    convocatorias.find(({ id }) => String(id) === seleccion) ?? convocatorias[0]

  return (
    <main>
      <h1>Disponibilidad docente</h1>

      {!sesion && <p role="status">{mensaje || 'Comprobando sesión…'}</p>}

      {sesion && !sesion.autenticado && (
        <form onSubmit={ingresar}>
          <p>
            <label>Usuario <input name="usuario" autoComplete="username" required /></label>
          </p>
          <p>
            <label>
              Contraseña{' '}
              <input name="clave" type="password" autoComplete="current-password" required />
            </label>
          </p>
          <button type="submit" disabled={ingresando}>Ingresar</button>
          <p role="status">{mensaje}</p>
        </form>
      )}

            {sesion?.autenticado && !convocatoria && !puedeGestionar && (
        <p>No tienes convocatorias asignadas.</p>
      )}

      {puedeGestionar && (
        <SeguimientoGestion
          recopilaciones={sesion.recopilaciones_gestion}
          puedeCambiarEstado={sesion.puede_cambiar_estado}
          csrfToken={sesion.csrfToken}
        />
      )}

      {convocatoria && (
        <>
          <label>
            Recopilación{' '}
            <select
              value={String(convocatoria.id)}
              onChange={(evento) => setSeleccion(evento.target.value)}
            >
              {convocatorias.map(({ id, periodo }) => (
                <option key={id} value={id}>{periodo}</option>
              ))}
            </select>
          </label>
          <Ficha key={convocatoria.id} convocatoria={convocatoria} csrfToken={sesion.csrfToken} />
        </>
      )}
    </main>
  )
}