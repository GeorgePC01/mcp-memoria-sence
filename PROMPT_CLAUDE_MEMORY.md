# Reglas Generales

- **Idioma:** Comunicarse siempre en español
- **NO incluir "Co-Authored-By: Claude" en commits**
- **NO incluir comentarios o referencias a "Claude" en mensajes de commit**
- Los commits deben aparecer como trabajo del usuario unicamente

---

# REGLA CRITICA: Sistema de Memoria Persistente (MCP claude-memory)

Este entorno utiliza un servidor MCP llamado `claude-memory` como cerebro persistente entre conversaciones.
Se trata de un servidor Python con base de datos SQLite local que almacena: proyectos, tickets, notas,
acciones ejecutadas y sesiones de trabajo. **Claude DEBE usar este sistema de forma AUTOMATICA y PROACTIVA
en TODAS las conversaciones**, sin esperar que el usuario lo pida.

La memoria MCP es la fuente de verdad para saber que se hizo antes, que quedo pendiente y cual es el
contexto actual del trabajo. Sin esta memoria, cada conversacion empieza desde cero.

---

## Instalacion (solo la primera vez en un equipo nuevo)

### Requisitos previos
- Python 3.10 o superior
- pip (gestor de paquetes de Python)
- git
- Claude Code con soporte MCP habilitado

### Pasos de instalacion

```bash
# 1. Clonar el repositorio del servidor MCP
git clone https://github.com/GeorgePC01/mcp-memoria-sence.git ~/mcp-servers

# 2. Crear entorno virtual aislado e instalar dependencias
cd ~/mcp-servers
python3 -m venv venv
source venv/bin/activate
pip install mcp

# 3. Verificar que el servidor arranca correctamente (debe mostrar output sin errores)
python3 memoria-server.py &
# Si arranca bien, detenerlo:
kill %1

# 4. Registrar el servidor MCP en Claude Code a nivel usuario (disponible en TODOS los proyectos)
claude mcp add --scope user claude-memory \
  ~/mcp-servers/venv/bin/python3 \
  ~/mcp-servers/memoria-server.py

# 5. Verificar que aparece en la lista de servidores MCP
claude mcp list
# Debe mostrar: claude-memory (user) - stdio
```

### Archivos generados
| Archivo | Ubicacion | Descripcion |
|---------|-----------|-------------|
| Servidor | `~/mcp-servers/memoria-server.py` | Codigo fuente del servidor MCP (Python) |
| Base de datos | `~/mcp-servers/memoria.db` | SQLite, se crea automaticamente al primer uso |
| Entorno virtual | `~/mcp-servers/venv/` | Python venv con MCP SDK |
| Configuracion | `~/.claude.json` | Registro del servidor MCP (scope user) |

### Actualizar a una version nueva
```bash
cd ~/mcp-servers
git pull origin master
# Reiniciar Claude Code para que tome los cambios
```

### Troubleshooting
- Si `claude mcp list` no muestra el servidor: verificar que `~/.claude.json` contiene la entrada en `mcpServers`
- Si las herramientas no aparecen: reiniciar Claude Code completamente
- Si hay errores de Python: verificar que el venv esta activo (`source ~/mcp-servers/venv/bin/activate && pip install mcp`)
- Para inspeccionar la BD manualmente: `sqlite3 ~/mcp-servers/memoria.db ".tables"`

---

## Herramientas disponibles (17)

### Proyectos (gestion de proyectos de trabajo)
| Herramienta | Descripcion |
|-------------|-------------|
| `crear_proyecto(nombre, descripcion, ambiente)` | Crea un proyecto nuevo. Se crean automaticamente tambien al guardar tickets |
| `listar_proyectos()` | Lista todos los proyectos con estadisticas de tickets |

### Tickets (bugs, tareas, incidencias, mejoras)
| Herramienta | Descripcion |
|-------------|-------------|
| `guardar_ticket(codigo, titulo, descripcion, proyecto, estado, prioridad, ...)` | Crea o actualiza un ticket. Si el proyecto no existe, lo crea |
| `buscar_ticket(codigo)` | Busca un ticket por codigo con todo su detalle, notas y acciones |
| `listar_tickets(proyecto, estado, prioridad, tags, limite)` | Lista tickets con filtros multiples |
| `cerrar_ticket(codigo, solucion, causa_raiz)` | Cierra un ticket documentando la solucion |
| `eliminar_ticket(codigo)` | Elimina un ticket y todo lo asociado (notas, acciones). Usar con precaucion |

### Notas (historial de observaciones, decisiones, diagnosticos)
| Herramienta | Descripcion |
|-------------|-------------|
| `agregar_nota(contenido, ticket_codigo, proyecto, tipo, ambiente, tags)` | Agrega una nota al historial |
| `buscar_notas(texto, ticket_codigo, proyecto, tipo, limite)` | Busca notas por cualquier criterio |

### Acciones (comandos ejecutados, deploys, backups)
| Herramienta | Descripcion |
|-------------|-------------|
| `registrar_accion(descripcion, ticket_codigo, proyecto, tipo, comando, resultado, ambiente, servidor)` | Registra una accion ejecutada |
| `listar_acciones(proyecto, ticket_codigo, tipo, ambiente, limite)` | Lista acciones con filtros |

### Sesiones (continuidad entre conversaciones)
| Herramienta | Descripcion |
|-------------|-------------|
| `iniciar_sesion(proyecto, resumen)` | Registra el inicio de una sesion de trabajo |
| `cerrar_sesion(sesion_id, trabajo_realizado, pendientes)` | Cierra la sesion con resumen y pendientes |
| `ver_ultima_sesion(proyecto)` | Muestra la ultima sesion de un proyecto |

### Contexto y busqueda
| Herramienta | Descripcion |
|-------------|-------------|
| `contexto_rapido(proyecto)` | **CLAVE:** Genera resumen completo (ultima sesion + tickets abiertos + notas recientes + ultimas acciones + stats). Usar al INICIO de cada conversacion |
| `buscar_general(texto, limite)` | Busqueda full-text en tickets, notas y acciones |
| `estadisticas(proyecto)` | Estadisticas numericas de la BD |

---

## Protocolo obligatorio de uso

### INICIO de cada conversacion (OBLIGATORIO, hacer SIEMPRE):
1. **`contexto_rapido(proyecto)`** — Obtener resumen inmediato del estado actual. Esta es la primera herramienta que se debe llamar. Da el panorama completo en una sola llamada.
2. **`iniciar_sesion(proyecto, resumen)`** — Registrar que se va a trabajar. El resumen debe describir el objetivo de la sesion.

### DURANTE el trabajo (usar segun corresponda):
- **Cuando se identifique un bug, tarea o incidencia:** `guardar_ticket()` con descripcion completa
- **Cuando se tome una decision de diseño o arquitectura:** `agregar_nota(tipo="DECISION")`
- **Cuando se diagnostique un problema:** `agregar_nota(tipo="DIAGNOSTICO")`
- **Cuando se ejecute un comando critico (deploy, backup, migracion, cambio de config):** `registrar_accion()` con el comando textual y su resultado
- **Cuando se encuentre algo importante:** `agregar_nota(tipo="OBSERVACION")`
- **Cuando algo quede pendiente:** `agregar_nota(tipo="PENDIENTE")`
- **Cuando se resuelva un ticket:** `cerrar_ticket()` con la solucion y causa raiz

### CIERRE de sesion (OBLIGATORIO, hacer SIEMPRE antes de terminar):
1. **`cerrar_sesion(sesion_id, trabajo_realizado, pendientes)`** — Documentar todo lo que se hizo y lo que falta. Ser especifico y detallado en los pendientes para que la proxima conversacion pueda retomar sin perder contexto.

---

## Valores permitidos

| Campo | Valores |
|-------|---------|
| **Tipos de nota** | `NOTA`, `DIAGNOSTICO`, `SOLUCION`, `OBSERVACION`, `DECISION`, `PENDIENTE` |
| **Tipos de accion** | `COMANDO`, `DEPLOY`, `BACKUP`, `ROLLBACK`, `CONFIG`, `INVESTIGACION`, `MIGRACION`, `TEST` |
| **Estados de ticket** | `ABIERTO`, `EN_PROCESO`, `RESUELTO`, `CERRADO` |
| **Prioridades de ticket** | `BAJA`, `MEDIA`, `ALTA`, `CRITICA` |
| **Ambientes** | `PRD`, `DEV`, `QA`, `STG`, `LOCAL` (o cualquier otro que aplique) |

---

## Reglas de comportamiento

1. **NUNCA esperar a que el usuario pida usar la memoria** — usarla proactivamente en cada conversacion
2. **Toda conversacion DEBE abrir y cerrar sesion** — esto garantiza continuidad
3. **`contexto_rapido()` es SIEMPRE la primera llamada** — antes de hacer cualquier otra cosa
4. **Registrar decisiones arquitectonicas como notas DECISION** — estas son las mas valiosas para futuras sesiones
5. **Si el usuario menciona un problema, bug o tarea nueva: crear un ticket automaticamente** con codigo descriptivo
6. **Si se resuelve algo: cerrar el ticket con solucion y causa raiz** — nunca dejar tickets abiertos sin necesidad
7. **Registrar comandos criticos como acciones** — especialmente deploys, backups, rollbacks, migraciones y cambios de configuracion
8. **Los pendientes en cierre de sesion deben ser ESPECIFICOS** — no escribir "seguir trabajando", sino exactamente QUE queda por hacer
9. **La base de datos es local por equipo** — cada maquina tiene su propia BD independiente, no se sincronizan
10. **Ante la duda, registrar** — es mejor tener una nota de mas que perder contexto entre conversaciones

---

## REGLA CRITICA: Proteccion de ambientes productivos

**Antes de ejecutar CUALQUIER cambio en produccion (PRD), Claude DEBE:**

1. **Avisar explicitamente** que el cambio afecta produccion y explicar el riesgo e impacto potencial
2. **Recomendar alternativas seguras** antes de proceder:
   - Probar primero en un ambiente inferior (DEV, QA, STG, LOCAL)
   - Hacer backup previo del archivo, tabla o dato afectado
   - Preparar un comando de rollback listo ANTES de ejecutar
   - Ejecutar en horario de menor impacto si aplica
3. **Pedir confirmacion explicita al usuario DOS VECES:**
   - Primera vez: presentar el plan detallado de lo que se va a hacer, los archivos/tablas/servicios afectados, y las recomendaciones de seguridad
   - Segunda vez: confirmar que el usuario leyo las recomendaciones y quiere proceder
4. **NUNCA ejecutar directamente** comandos destructivos en produccion (DELETE, DROP, TRUNCATE, rm, overwrite) sin las dos confirmaciones previas
5. **Siempre dar recomendaciones proactivas** sobre como minimizar riesgo: backups, ventanas de mantenimiento, monitoreo post-cambio, pruebas previas en ambientes inferiores
6. **Registrar toda accion en produccion** usando `registrar_accion(ambiente="PRD")` con el comando exacto y su resultado

**Ejemplos de lo que REQUIERE doble confirmacion:**
- Modificar archivos en servidores de produccion
- Ejecutar queries que modifican datos (UPDATE, DELETE, INSERT en PRD)
- Cambios de configuracion en servicios productivos
- Deploys, migraciones, cambios de schema en bases de datos productivas
- Reinicio de servicios en produccion
- Cualquier operacion irreversible o dificil de revertir
