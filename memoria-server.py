#!/usr/bin/env python3
"""
Servidor MCP - Sistema de Memoria Persistente para Claude Code
==============================================================
Almacena tickets, notas, historial de trabajo y contexto de proyectos
en una base de datos SQLite local. Diseñado para ser reutilizado en
cualquier equipo y cualquier proyecto.

Repositorio: https://github.com/GeorgePC01/mcp-memoria-sence
Version: 2.0.0
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# ── Configuracion ──────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent / "memoria.db"

# ── Inicializar servidor MCP ───────────────────────────────────────────────
mcp = FastMCP(
    "claude-memory",
    instructions=(
        "Sistema de memoria persistente para Claude Code. "
        "Almacena proyectos, tickets, notas, acciones y sesiones de trabajo "
        "en SQLite local para mantener continuidad entre conversaciones. Version 2.0.0"
    )
)


# ── Funciones de base de datos ─────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    """Obtiene conexion a la base de datos con row_factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Inicializa el esquema de la base de datos."""
    conn = get_db()
    conn.executescript("""
        -- Tabla de proyectos
        CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            descripcion TEXT,
            ambiente TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        -- Tabla de tickets
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            proyecto_id INTEGER,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            estado TEXT DEFAULT 'ABIERTO',
            prioridad TEXT DEFAULT 'MEDIA',
            fecha_apertura TEXT,
            fecha_cierre TEXT,
            causa_raiz TEXT,
            solucion TEXT,
            notas TEXT,
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (proyecto_id) REFERENCES proyectos(id)
        );

        -- Tabla de notas / historial de trabajo
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            proyecto_id INTEGER,
            tipo TEXT DEFAULT 'NOTA',
            contenido TEXT NOT NULL,
            ambiente TEXT,
            fecha TEXT DEFAULT (datetime('now', 'localtime')),
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (ticket_id) REFERENCES tickets(id),
            FOREIGN KEY (proyecto_id) REFERENCES proyectos(id)
        );

        -- Tabla de comandos / acciones ejecutadas
        CREATE TABLE IF NOT EXISTS acciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            proyecto_id INTEGER,
            tipo TEXT DEFAULT 'COMANDO',
            descripcion TEXT NOT NULL,
            comando TEXT,
            resultado TEXT,
            ambiente TEXT,
            servidor TEXT,
            fecha TEXT DEFAULT (datetime('now', 'localtime')),
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (ticket_id) REFERENCES tickets(id),
            FOREIGN KEY (proyecto_id) REFERENCES proyectos(id)
        );

        -- Tabla de credenciales / conexiones (referencias, NO passwords)
        CREATE TABLE IF NOT EXISTS conexiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER,
            nombre TEXT NOT NULL,
            tipo TEXT,
            host TEXT,
            puerto INTEGER,
            usuario TEXT,
            notas TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (proyecto_id) REFERENCES proyectos(id)
        );

        -- Tabla de contexto de sesion
        CREATE TABLE IF NOT EXISTS sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER,
            resumen TEXT NOT NULL,
            trabajo_realizado TEXT,
            pendientes TEXT,
            fecha_inicio TEXT DEFAULT (datetime('now', 'localtime')),
            fecha_fin TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (proyecto_id) REFERENCES proyectos(id)
        );

        -- Indices para busqueda rapida
        CREATE INDEX IF NOT EXISTS idx_tickets_codigo ON tickets(codigo);
        CREATE INDEX IF NOT EXISTS idx_tickets_estado ON tickets(estado);
        CREATE INDEX IF NOT EXISTS idx_tickets_proyecto ON tickets(proyecto_id);
        CREATE INDEX IF NOT EXISTS idx_notas_ticket ON notas(ticket_id);
        CREATE INDEX IF NOT EXISTS idx_notas_proyecto ON notas(proyecto_id);
        CREATE INDEX IF NOT EXISTS idx_notas_tipo ON notas(tipo);
        CREATE INDEX IF NOT EXISTS idx_acciones_ticket ON acciones(ticket_id);
        CREATE INDEX IF NOT EXISTS idx_acciones_fecha ON acciones(fecha);
        CREATE INDEX IF NOT EXISTS idx_sesiones_proyecto ON sesiones(proyecto_id);

        -- Trigger para actualizar updated_at en tickets
        CREATE TRIGGER IF NOT EXISTS trg_tickets_updated
        AFTER UPDATE ON tickets
        BEGIN
            UPDATE tickets SET updated_at = datetime('now', 'localtime')
            WHERE id = NEW.id;
        END;

        -- Trigger para actualizar updated_at en proyectos
        CREATE TRIGGER IF NOT EXISTS trg_proyectos_updated
        AFTER UPDATE ON proyectos
        BEGIN
            UPDATE proyectos SET updated_at = datetime('now', 'localtime')
            WHERE id = NEW.id;
        END;
    """)
    conn.commit()
    conn.close()


# ── Funciones auxiliares ───────────────────────────────────────────────────
def _resolver_proyecto_id(conn, proyecto: str):
    """Busca proyecto_id por nombre. Retorna None si no se encuentra."""
    if not proyecto:
        return None
    row = conn.execute("SELECT id FROM proyectos WHERE nombre LIKE ?", (f"%{proyecto}%",)).fetchone()
    return row['id'] if row else None


def _resolver_ticket_y_proyecto(conn, ticket_codigo: str, proyecto: str = ""):
    """Resuelve ticket_id y proyecto_id a partir de codigo de ticket y/o nombre de proyecto."""
    ticket_id = None
    proyecto_id = None

    if ticket_codigo:
        row = conn.execute("SELECT id, proyecto_id FROM tickets WHERE codigo = ?", (ticket_codigo,)).fetchone()
        if row:
            ticket_id = row['id']
            proyecto_id = row['proyecto_id']

    if proyecto and not proyecto_id:
        proyecto_id = _resolver_proyecto_id(conn, proyecto)

    return ticket_id, proyecto_id


# ── Herramientas MCP: PROYECTOS ───────────────────────────────────────────

@mcp.tool()
def crear_proyecto(nombre: str, descripcion: str = "", ambiente: str = "") -> str:
    """Crea un nuevo proyecto en la base de datos.

    Args:
        nombre: Nombre del proyecto (ej: 'MiApp', 'Backend API', 'Infraestructura')
        descripcion: Descripcion del proyecto
        ambiente: Ambiente (PRD, DEV, QA, STG, LOCAL, etc.)
    """
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO proyectos (nombre, descripcion, ambiente) VALUES (?, ?, ?)",
            (nombre, descripcion, ambiente)
        )
        conn.commit()
        return f"Proyecto '{nombre}' creado exitosamente."
    except sqlite3.IntegrityError:
        return f"Error: El proyecto '{nombre}' ya existe."
    finally:
        conn.close()


@mcp.tool()
def listar_proyectos() -> str:
    """Lista todos los proyectos registrados con sus estadisticas basicas."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM proyectos ORDER BY nombre").fetchall()
    if not rows:
        conn.close()
        return "No hay proyectos registrados."
    result = []
    for r in rows:
        tickets_abiertos = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE proyecto_id=? AND estado IN ('ABIERTO','EN_PROCESO')",
            (r['id'],)
        ).fetchone()[0]
        total_tickets = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE proyecto_id=?", (r['id'],)
        ).fetchone()[0]
        result.append(
            f"[{r['id']}] {r['nombre']} | {r['descripcion'] or '-'} | "
            f"Amb: {r['ambiente'] or '-'} | Tickets: {tickets_abiertos} abiertos / {total_tickets} total | "
            f"Creado: {r['created_at']}"
        )
    conn.close()
    return "\n".join(result)


# ── Herramientas MCP: TICKETS ─────────────────────────────────────────────

@mcp.tool()
def guardar_ticket(
    codigo: str,
    titulo: str,
    descripcion: str = "",
    proyecto: str = "",
    estado: str = "ABIERTO",
    prioridad: str = "MEDIA",
    fecha_apertura: str = "",
    causa_raiz: str = "",
    solucion: str = "",
    notas: str = "",
    tags: str = ""
) -> str:
    """Guarda o actualiza un ticket en la base de datos.

    Si el ticket ya existe (por codigo), lo actualiza.
    Si no existe, lo crea. Si el proyecto no existe, lo crea automaticamente.

    Args:
        codigo: Codigo unico del ticket (ej: 'BUG-001', 'TASK-042', 'INC-007')
        titulo: Titulo o asunto del ticket
        descripcion: Descripcion detallada del problema o tarea
        proyecto: Nombre del proyecto asociado (se crea automaticamente si no existe)
        estado: Estado actual (ABIERTO, EN_PROCESO, RESUELTO, CERRADO)
        prioridad: Prioridad (BAJA, MEDIA, ALTA, CRITICA)
        fecha_apertura: Fecha de apertura (YYYY-MM-DD). Si no se indica, usa la fecha actual
        causa_raiz: Causa raiz identificada del problema
        solucion: Solucion aplicada o propuesta
        notas: Notas adicionales de contexto
        tags: Tags separados por coma (ej: 'backend,urgente,mysql')
    """
    conn = get_db()

    # Buscar proyecto_id si se especifico
    proyecto_id = None
    if proyecto:
        row = conn.execute("SELECT id FROM proyectos WHERE nombre = ?", (proyecto,)).fetchone()
        if row:
            proyecto_id = row['id']
        else:
            conn.execute("INSERT INTO proyectos (nombre) VALUES (?)", (proyecto,))
            conn.commit()
            proyecto_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Verificar si el ticket ya existe
    existing = conn.execute("SELECT id FROM tickets WHERE codigo = ?", (codigo,)).fetchone()

    if existing:
        updates = []
        params = []
        if titulo:
            updates.append("titulo = ?"); params.append(titulo)
        if descripcion:
            updates.append("descripcion = ?"); params.append(descripcion)
        if proyecto_id is not None:
            updates.append("proyecto_id = ?"); params.append(proyecto_id)
        if estado:
            updates.append("estado = ?"); params.append(estado)
        if prioridad:
            updates.append("prioridad = ?"); params.append(prioridad)
        if fecha_apertura:
            updates.append("fecha_apertura = ?"); params.append(fecha_apertura)
        if causa_raiz:
            updates.append("causa_raiz = ?"); params.append(causa_raiz)
        if solucion:
            updates.append("solucion = ?"); params.append(solucion)
        if notas:
            updates.append("notas = ?"); params.append(notas)
        if tags:
            updates.append("tags = ?"); params.append(tags)

        if updates:
            params.append(codigo)
            conn.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE codigo = ?", params)
            conn.commit()
            conn.close()
            return f"Ticket {codigo} actualizado exitosamente."
        else:
            conn.close()
            return f"Ticket {codigo} existe pero no se proporcionaron campos para actualizar."
    else:
        conn.execute(
            """INSERT INTO tickets (codigo, titulo, descripcion, proyecto_id, estado, prioridad,
               fecha_apertura, causa_raiz, solucion, notas, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (codigo, titulo, descripcion, proyecto_id, estado, prioridad,
             fecha_apertura or datetime.now().strftime("%Y-%m-%d"),
             causa_raiz, solucion, notas, tags)
        )
        conn.commit()
        conn.close()
        return f"Ticket {codigo} creado exitosamente."


@mcp.tool()
def buscar_ticket(codigo: str) -> str:
    """Busca un ticket por su codigo y retorna toda su informacion incluyendo notas y acciones asociadas.

    Args:
        codigo: Codigo del ticket (ej: 'BUG-001')
    """
    conn = get_db()
    row = conn.execute("""
        SELECT t.*, p.nombre as proyecto_nombre
        FROM tickets t
        LEFT JOIN proyectos p ON t.proyecto_id = p.id
        WHERE t.codigo = ?
    """, (codigo,)).fetchone()

    if not row:
        conn.close()
        return f"Ticket {codigo} no encontrado."

    notas = conn.execute(
        "SELECT * FROM notas WHERE ticket_id = ? ORDER BY fecha DESC", (row['id'],)
    ).fetchall()

    acciones = conn.execute(
        "SELECT * FROM acciones WHERE ticket_id = ? ORDER BY fecha DESC", (row['id'],)
    ).fetchall()

    conn.close()

    result = [
        f"=== TICKET {row['codigo']} ===",
        f"Titulo: {row['titulo']}",
        f"Proyecto: {row['proyecto_nombre'] or '-'}",
        f"Estado: {row['estado']} | Prioridad: {row['prioridad']}",
        f"Fecha apertura: {row['fecha_apertura'] or '-'}",
        f"Fecha cierre: {row['fecha_cierre'] or '-'}",
        f"",
        f"-- Descripcion --",
        f"{row['descripcion'] or '(sin descripcion)'}",
        f"",
        f"-- Causa raiz --",
        f"{row['causa_raiz'] or '(no identificada)'}",
        f"",
        f"-- Solucion --",
        f"{row['solucion'] or '(pendiente)'}",
        f"",
        f"-- Notas --",
        f"{row['notas'] or '(sin notas)'}",
        f"",
        f"Tags: {row['tags'] or '-'}",
        f"Creado: {row['created_at']} | Actualizado: {row['updated_at']}",
    ]

    if notas:
        result.append(f"\n-- Historial de notas ({len(notas)}) --")
        for n in notas:
            result.append(f"  [{n['fecha']}] ({n['tipo']}) {n['contenido']}")

    if acciones:
        result.append(f"\n-- Acciones registradas ({len(acciones)}) --")
        for a in acciones:
            result.append(f"  [{a['fecha']}] {a['descripcion']}")
            if a['comando']:
                result.append(f"    CMD: {a['comando']}")

    return "\n".join(result)


@mcp.tool()
def listar_tickets(
    proyecto: str = "",
    estado: str = "",
    prioridad: str = "",
    tags: str = "",
    limite: int = 20
) -> str:
    """Lista tickets filtrados por proyecto, estado, prioridad o tags.

    Args:
        proyecto: Filtrar por nombre de proyecto
        estado: Filtrar por estado (ABIERTO, EN_PROCESO, RESUELTO, CERRADO)
        prioridad: Filtrar por prioridad (BAJA, MEDIA, ALTA, CRITICA)
        tags: Filtrar por tag (busca coincidencia parcial)
        limite: Numero maximo de resultados (default: 20)
    """
    conn = get_db()
    query = """
        SELECT t.codigo, t.titulo, t.estado, t.prioridad, t.fecha_apertura, t.tags,
               p.nombre as proyecto_nombre
        FROM tickets t
        LEFT JOIN proyectos p ON t.proyecto_id = p.id
        WHERE 1=1
    """
    params = []

    if proyecto:
        query += " AND p.nombre LIKE ?"
        params.append(f"%{proyecto}%")
    if estado:
        query += " AND t.estado = ?"
        params.append(estado)
    if prioridad:
        query += " AND t.prioridad = ?"
        params.append(prioridad)
    if tags:
        query += " AND t.tags LIKE ?"
        params.append(f"%{tags}%")

    query += " ORDER BY t.updated_at DESC LIMIT ?"
    params.append(limite)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return "No se encontraron tickets con los filtros especificados."

    result = [f"{'Codigo':<12} {'Estado':<12} {'Prioridad':<10} {'Proyecto':<15} {'Titulo'}"]
    result.append("-" * 80)
    for r in rows:
        result.append(
            f"{r['codigo']:<12} {r['estado']:<12} {r['prioridad']:<10} "
            f"{(r['proyecto_nombre'] or '-'):<15} {r['titulo'][:40]}"
        )

    return "\n".join(result)


@mcp.tool()
def cerrar_ticket(codigo: str, solucion: str = "", causa_raiz: str = "") -> str:
    """Cierra un ticket registrando la solucion y causa raiz.

    Args:
        codigo: Codigo del ticket
        solucion: Solucion aplicada
        causa_raiz: Causa raiz del problema
    """
    conn = get_db()
    existing = conn.execute("SELECT id FROM tickets WHERE codigo = ?", (codigo,)).fetchone()
    if not existing:
        conn.close()
        return f"Ticket {codigo} no encontrado."

    updates = ["estado = 'CERRADO'", "fecha_cierre = datetime('now', 'localtime')"]
    params = []
    if solucion:
        updates.append("solucion = ?")
        params.append(solucion)
    if causa_raiz:
        updates.append("causa_raiz = ?")
        params.append(causa_raiz)

    params.append(codigo)
    conn.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE codigo = ?", params)
    conn.commit()
    conn.close()
    return f"Ticket {codigo} cerrado exitosamente."


@mcp.tool()
def eliminar_ticket(codigo: str) -> str:
    """Elimina un ticket y todas sus notas y acciones asociadas. USAR CON PRECAUCION.

    Args:
        codigo: Codigo del ticket a eliminar
    """
    conn = get_db()
    row = conn.execute("SELECT id FROM tickets WHERE codigo = ?", (codigo,)).fetchone()
    if not row:
        conn.close()
        return f"Ticket {codigo} no encontrado."

    ticket_id = row['id']
    notas_del = conn.execute("DELETE FROM notas WHERE ticket_id = ?", (ticket_id,)).rowcount
    acciones_del = conn.execute("DELETE FROM acciones WHERE ticket_id = ?", (ticket_id,)).rowcount
    conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    return (
        f"Ticket {codigo} eliminado. "
        f"Se eliminaron tambien {notas_del} nota(s) y {acciones_del} accion(es) asociadas."
    )


# ── Herramientas MCP: NOTAS ───────────────────────────────────────────────

@mcp.tool()
def agregar_nota(
    contenido: str,
    ticket_codigo: str = "",
    proyecto: str = "",
    tipo: str = "NOTA",
    ambiente: str = "",
    tags: str = ""
) -> str:
    """Agrega una nota al historial. Puede estar asociada a un ticket y/o proyecto.

    Args:
        contenido: Contenido de la nota (ser descriptivo y detallado)
        ticket_codigo: Codigo del ticket asociado (opcional)
        proyecto: Nombre del proyecto asociado (opcional)
        tipo: Tipo de nota (NOTA, DIAGNOSTICO, SOLUCION, OBSERVACION, DECISION, PENDIENTE)
        ambiente: Ambiente donde aplica (PRD, DEV, QA, STG, LOCAL)
        tags: Tags separados por coma
    """
    conn = get_db()
    ticket_id, proyecto_id = _resolver_ticket_y_proyecto(conn, ticket_codigo, proyecto)

    conn.execute(
        """INSERT INTO notas (ticket_id, proyecto_id, tipo, contenido, ambiente, tags)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ticket_id, proyecto_id, tipo, contenido, ambiente, tags)
    )
    conn.commit()
    conn.close()

    ref = f" (ticket {ticket_codigo})" if ticket_codigo else ""
    return f"Nota guardada exitosamente{ref}."


@mcp.tool()
def buscar_notas(
    texto: str = "",
    ticket_codigo: str = "",
    proyecto: str = "",
    tipo: str = "",
    limite: int = 20
) -> str:
    """Busca notas por texto, ticket, proyecto o tipo.

    Args:
        texto: Texto a buscar en el contenido
        ticket_codigo: Filtrar por codigo de ticket
        proyecto: Filtrar por nombre de proyecto
        tipo: Filtrar por tipo (NOTA, DIAGNOSTICO, SOLUCION, OBSERVACION, DECISION, PENDIENTE)
        limite: Numero maximo de resultados
    """
    conn = get_db()
    query = """
        SELECT n.*, t.codigo as ticket_codigo, p.nombre as proyecto_nombre
        FROM notas n
        LEFT JOIN tickets t ON n.ticket_id = t.id
        LEFT JOIN proyectos p ON n.proyecto_id = p.id
        WHERE 1=1
    """
    params = []

    if texto:
        query += " AND n.contenido LIKE ?"
        params.append(f"%{texto}%")
    if ticket_codigo:
        query += " AND t.codigo = ?"
        params.append(ticket_codigo)
    if proyecto:
        query += " AND p.nombre LIKE ?"
        params.append(f"%{proyecto}%")
    if tipo:
        query += " AND n.tipo = ?"
        params.append(tipo)

    query += " ORDER BY n.fecha DESC LIMIT ?"
    params.append(limite)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return "No se encontraron notas con los filtros especificados."

    result = []
    for r in rows:
        header = f"[{r['fecha']}] ({r['tipo']})"
        if r['ticket_codigo']:
            header += f" #{r['ticket_codigo']}"
        if r['proyecto_nombre']:
            header += f" @{r['proyecto_nombre']}"
        if r['ambiente']:
            header += f" [{r['ambiente']}]"
        result.append(header)
        result.append(f"  {r['contenido']}")
        result.append("")

    return "\n".join(result)


# ── Herramientas MCP: ACCIONES ─────────────────────────────────────────────

@mcp.tool()
def registrar_accion(
    descripcion: str,
    ticket_codigo: str = "",
    proyecto: str = "",
    tipo: str = "COMANDO",
    comando: str = "",
    resultado: str = "",
    ambiente: str = "",
    servidor: str = ""
) -> str:
    """Registra una accion o comando ejecutado en el historial.

    Args:
        descripcion: Descripcion clara de la accion realizada
        ticket_codigo: Codigo del ticket asociado
        proyecto: Nombre del proyecto
        tipo: Tipo (COMANDO, DEPLOY, BACKUP, ROLLBACK, CONFIG, INVESTIGACION, MIGRACION, TEST)
        comando: Comando ejecutado (copiar textual)
        resultado: Resultado obtenido (exito, error, output relevante)
        ambiente: Ambiente (PRD, DEV, QA, STG, LOCAL)
        servidor: Servidor o host donde se ejecuto
    """
    conn = get_db()
    ticket_id, proyecto_id = _resolver_ticket_y_proyecto(conn, ticket_codigo, proyecto)

    conn.execute(
        """INSERT INTO acciones (ticket_id, proyecto_id, tipo, descripcion, comando, resultado, ambiente, servidor)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticket_id, proyecto_id, tipo, descripcion, comando, resultado, ambiente, servidor)
    )
    conn.commit()
    conn.close()
    return f"Accion registrada exitosamente."


@mcp.tool()
def listar_acciones(
    proyecto: str = "",
    ticket_codigo: str = "",
    tipo: str = "",
    ambiente: str = "",
    limite: int = 20
) -> str:
    """Lista acciones registradas filtradas por proyecto, ticket, tipo o ambiente.

    Args:
        proyecto: Filtrar por nombre de proyecto
        ticket_codigo: Filtrar por codigo de ticket
        tipo: Filtrar por tipo (COMANDO, DEPLOY, BACKUP, ROLLBACK, CONFIG, INVESTIGACION, MIGRACION, TEST)
        ambiente: Filtrar por ambiente (PRD, DEV, QA, STG, LOCAL)
        limite: Numero maximo de resultados
    """
    conn = get_db()
    query = """
        SELECT a.*, t.codigo as ticket_codigo, p.nombre as proyecto_nombre
        FROM acciones a
        LEFT JOIN tickets t ON a.ticket_id = t.id
        LEFT JOIN proyectos p ON a.proyecto_id = p.id
        WHERE 1=1
    """
    params = []

    if proyecto:
        query += " AND p.nombre LIKE ?"
        params.append(f"%{proyecto}%")
    if ticket_codigo:
        query += " AND t.codigo = ?"
        params.append(ticket_codigo)
    if tipo:
        query += " AND a.tipo = ?"
        params.append(tipo)
    if ambiente:
        query += " AND a.ambiente = ?"
        params.append(ambiente)

    query += " ORDER BY a.fecha DESC LIMIT ?"
    params.append(limite)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return "No se encontraron acciones con los filtros especificados."

    result = []
    for r in rows:
        header = f"[{r['fecha']}] ({r['tipo']})"
        if r['ticket_codigo']:
            header += f" #{r['ticket_codigo']}"
        if r['proyecto_nombre']:
            header += f" @{r['proyecto_nombre']}"
        if r['ambiente']:
            header += f" [{r['ambiente']}]"
        if r['servidor']:
            header += f" srv:{r['servidor']}"
        result.append(header)
        result.append(f"  {r['descripcion']}")
        if r['comando']:
            result.append(f"  CMD: {r['comando']}")
        if r['resultado']:
            result.append(f"  RES: {r['resultado'][:200]}")
        result.append("")

    return "\n".join(result)


# ── Herramientas MCP: SESIONES ─────────────────────────────────────────────

@mcp.tool()
def iniciar_sesion(proyecto: str, resumen: str) -> str:
    """Registra el inicio de una sesion de trabajo. LLAMAR SIEMPRE al comenzar a trabajar.

    Args:
        proyecto: Nombre del proyecto (se crea automaticamente si no existe)
        resumen: Resumen de lo que se va a trabajar en esta sesion
    """
    conn = get_db()
    proyecto_id = _resolver_proyecto_id(conn, proyecto)

    if not proyecto_id and proyecto:
        conn.execute("INSERT INTO proyectos (nombre) VALUES (?)", (proyecto,))
        conn.commit()
        proyecto_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO sesiones (proyecto_id, resumen) VALUES (?, ?)",
        (proyecto_id, resumen)
    )
    conn.commit()
    sesion_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return f"Sesion #{sesion_id} iniciada para proyecto '{proyecto}'."


@mcp.tool()
def cerrar_sesion(sesion_id: int, trabajo_realizado: str, pendientes: str = "") -> str:
    """Cierra una sesion de trabajo registrando lo realizado y pendientes.
    LLAMAR SIEMPRE al terminar de trabajar.

    Args:
        sesion_id: ID de la sesion a cerrar (proporcionado al iniciar_sesion)
        trabajo_realizado: Resumen detallado del trabajo realizado en esta sesion
        pendientes: Trabajo pendiente para la proxima sesion (ser especifico)
    """
    conn = get_db()
    existing = conn.execute("SELECT id FROM sesiones WHERE id = ?", (sesion_id,)).fetchone()
    if not existing:
        conn.close()
        return f"Sesion #{sesion_id} no encontrada."

    conn.execute(
        """UPDATE sesiones SET trabajo_realizado = ?, pendientes = ?,
           fecha_fin = datetime('now', 'localtime') WHERE id = ?""",
        (trabajo_realizado, pendientes, sesion_id)
    )
    conn.commit()
    conn.close()
    return f"Sesion #{sesion_id} cerrada exitosamente."


@mcp.tool()
def ver_ultima_sesion(proyecto: str = "") -> str:
    """Muestra la ultima sesion de trabajo. Util para retomar contexto al iniciar.

    Args:
        proyecto: Nombre del proyecto (opcional, muestra la mas reciente si no se especifica)
    """
    conn = get_db()
    query = """
        SELECT s.*, p.nombre as proyecto_nombre
        FROM sesiones s
        LEFT JOIN proyectos p ON s.proyecto_id = p.id
    """
    params = []
    if proyecto:
        query += " WHERE p.nombre LIKE ?"
        params.append(f"%{proyecto}%")
    query += " ORDER BY s.fecha_inicio DESC LIMIT 1"

    row = conn.execute(query, params).fetchone()
    conn.close()

    if not row:
        return "No hay sesiones registradas."

    result = [
        f"=== SESION #{row['id']} ===",
        f"Proyecto: {row['proyecto_nombre'] or '-'}",
        f"Inicio: {row['fecha_inicio']}",
        f"Fin: {row['fecha_fin'] or '(en curso)'}",
        f"",
        f"-- Resumen --",
        f"{row['resumen']}",
        f"",
        f"-- Trabajo realizado --",
        f"{row['trabajo_realizado'] or '(no registrado)'}",
        f"",
        f"-- Pendientes --",
        f"{row['pendientes'] or '(ninguno)'}",
    ]
    return "\n".join(result)


# ── Herramientas MCP: CONTEXTO RAPIDO ─────────────────────────────────────

@mcp.tool()
def contexto_rapido(proyecto: str = "") -> str:
    """Genera un resumen completo del estado actual para retomar trabajo rapidamente.
    Incluye: ultima sesion, tickets abiertos, notas recientes y ultimas acciones.
    USAR AL INICIO DE CADA CONVERSACION para obtener contexto inmediato.

    Args:
        proyecto: Nombre del proyecto (opcional, muestra todo si no se especifica)
    """
    conn = get_db()
    result = []

    # --- Ultima sesion ---
    query_sesion = """
        SELECT s.*, p.nombre as proyecto_nombre
        FROM sesiones s LEFT JOIN proyectos p ON s.proyecto_id = p.id
    """
    params_sesion = []
    if proyecto:
        query_sesion += " WHERE p.nombre LIKE ?"
        params_sesion.append(f"%{proyecto}%")
    query_sesion += " ORDER BY s.fecha_inicio DESC LIMIT 1"
    sesion = conn.execute(query_sesion, params_sesion).fetchone()

    if sesion:
        result.append("=== ULTIMA SESION ===")
        result.append(f"Proyecto: {sesion['proyecto_nombre'] or '-'} | Inicio: {sesion['fecha_inicio']} | Fin: {sesion['fecha_fin'] or '(en curso)'}")
        result.append(f"Resumen: {sesion['resumen']}")
        if sesion['trabajo_realizado']:
            result.append(f"Realizado: {sesion['trabajo_realizado']}")
        if sesion['pendientes']:
            result.append(f"PENDIENTES: {sesion['pendientes']}")
        result.append("")

    # --- Tickets abiertos ---
    query_tickets = """
        SELECT t.codigo, t.titulo, t.estado, t.prioridad, p.nombre as proyecto_nombre
        FROM tickets t LEFT JOIN proyectos p ON t.proyecto_id = p.id
        WHERE t.estado IN ('ABIERTO', 'EN_PROCESO')
    """
    params_tickets = []
    if proyecto:
        query_tickets += " AND p.nombre LIKE ?"
        params_tickets.append(f"%{proyecto}%")
    query_tickets += " ORDER BY CASE t.prioridad WHEN 'CRITICA' THEN 1 WHEN 'ALTA' THEN 2 WHEN 'MEDIA' THEN 3 ELSE 4 END, t.updated_at DESC LIMIT 10"
    tickets = conn.execute(query_tickets, params_tickets).fetchall()

    if tickets:
        result.append(f"=== TICKETS ABIERTOS ({len(tickets)}) ===")
        for t in tickets:
            result.append(f"  [{t['codigo']}] ({t['prioridad']}) {t['titulo']} @{t['proyecto_nombre'] or '-'}")
        result.append("")

    # --- Notas recientes (ultimas 5) ---
    query_notas = """
        SELECT n.contenido, n.tipo, n.fecha, t.codigo as ticket_codigo, p.nombre as proyecto_nombre
        FROM notas n
        LEFT JOIN tickets t ON n.ticket_id = t.id
        LEFT JOIN proyectos p ON n.proyecto_id = p.id
    """
    params_notas = []
    if proyecto:
        query_notas += " WHERE p.nombre LIKE ?"
        params_notas.append(f"%{proyecto}%")
    query_notas += " ORDER BY n.fecha DESC LIMIT 5"
    notas = conn.execute(query_notas, params_notas).fetchall()

    if notas:
        result.append("=== NOTAS RECIENTES ===")
        for n in notas:
            ref = f" #{n['ticket_codigo']}" if n['ticket_codigo'] else ""
            proj = f" @{n['proyecto_nombre']}" if n['proyecto_nombre'] else ""
            result.append(f"  [{n['fecha']}] ({n['tipo']}){ref}{proj}")
            result.append(f"    {n['contenido'][:150]}")
        result.append("")

    # --- Ultimas acciones (ultimas 5) ---
    query_acciones = """
        SELECT a.descripcion, a.tipo, a.fecha, a.ambiente, a.servidor,
               t.codigo as ticket_codigo, p.nombre as proyecto_nombre
        FROM acciones a
        LEFT JOIN tickets t ON a.ticket_id = t.id
        LEFT JOIN proyectos p ON a.proyecto_id = p.id
    """
    params_acciones = []
    if proyecto:
        query_acciones += " WHERE p.nombre LIKE ?"
        params_acciones.append(f"%{proyecto}%")
    query_acciones += " ORDER BY a.fecha DESC LIMIT 5"
    acciones = conn.execute(query_acciones, params_acciones).fetchall()

    if acciones:
        result.append("=== ULTIMAS ACCIONES ===")
        for a in acciones:
            ref = f" #{a['ticket_codigo']}" if a['ticket_codigo'] else ""
            amb = f" [{a['ambiente']}]" if a['ambiente'] else ""
            result.append(f"  [{a['fecha']}] ({a['tipo']}){ref}{amb} {a['descripcion'][:100]}")
        result.append("")

    # --- Estadisticas ---
    if proyecto:
        pid_row = conn.execute("SELECT id FROM proyectos WHERE nombre LIKE ?", (f"%{proyecto}%",)).fetchone()
        if pid_row:
            pid = pid_row['id']
            total = conn.execute("SELECT COUNT(*) FROM tickets WHERE proyecto_id=?", (pid,)).fetchone()[0]
            abiertos = conn.execute("SELECT COUNT(*) FROM tickets WHERE proyecto_id=? AND estado IN ('ABIERTO','EN_PROCESO')", (pid,)).fetchone()[0]
            total_notas = conn.execute("SELECT COUNT(*) FROM notas WHERE proyecto_id=?", (pid,)).fetchone()[0]
            total_sesiones = conn.execute("SELECT COUNT(*) FROM sesiones WHERE proyecto_id=?", (pid,)).fetchone()[0]
            result.append(f"=== STATS: {total} tickets ({abiertos} abiertos) | {total_notas} notas | {total_sesiones} sesiones ===")
    else:
        total_proy = conn.execute("SELECT COUNT(*) FROM proyectos").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        abiertos = conn.execute("SELECT COUNT(*) FROM tickets WHERE estado IN ('ABIERTO','EN_PROCESO')").fetchone()[0]
        result.append(f"=== STATS GLOBALES: {total_proy} proyectos | {total} tickets ({abiertos} abiertos) ===")

    conn.close()

    if not result:
        return "Base de datos vacia. Es la primera sesion en este equipo."

    return "\n".join(result)


# ── Herramientas MCP: BUSQUEDA GENERAL ─────────────────────────────────────

@mcp.tool()
def buscar_general(texto: str, limite: int = 15) -> str:
    """Busqueda full-text en tickets, notas y acciones. Busca en todos los campos relevantes.

    Args:
        texto: Texto a buscar
        limite: Numero maximo de resultados por tabla
    """
    conn = get_db()
    results = []

    tickets = conn.execute("""
        SELECT codigo, titulo, estado, descripcion
        FROM tickets
        WHERE codigo LIKE ? OR titulo LIKE ? OR descripcion LIKE ?
              OR causa_raiz LIKE ? OR solucion LIKE ? OR notas LIKE ?
        ORDER BY updated_at DESC LIMIT ?
    """, (f"%{texto}%",) * 6 + (limite,)).fetchall()

    if tickets:
        results.append("=== TICKETS ===")
        for t in tickets:
            results.append(f"  [{t['codigo']}] ({t['estado']}) {t['titulo']}")
            if t['descripcion'] and texto.lower() in t['descripcion'].lower():
                idx = t['descripcion'].lower().find(texto.lower())
                start = max(0, idx - 50)
                end = min(len(t['descripcion']), idx + len(texto) + 50)
                results.append(f"    ...{t['descripcion'][start:end]}...")
        results.append("")

    notas = conn.execute("""
        SELECT n.contenido, n.tipo, n.fecha, t.codigo as ticket_codigo
        FROM notas n
        LEFT JOIN tickets t ON n.ticket_id = t.id
        WHERE n.contenido LIKE ?
        ORDER BY n.fecha DESC LIMIT ?
    """, (f"%{texto}%", limite)).fetchall()

    if notas:
        results.append("=== NOTAS ===")
        for n in notas:
            ref = f" #{n['ticket_codigo']}" if n['ticket_codigo'] else ""
            results.append(f"  [{n['fecha']}] ({n['tipo']}){ref}")
            idx = n['contenido'].lower().find(texto.lower())
            start = max(0, idx - 60)
            end = min(len(n['contenido']), idx + len(texto) + 60)
            results.append(f"    ...{n['contenido'][start:end]}...")
        results.append("")

    acciones = conn.execute("""
        SELECT a.descripcion, a.tipo, a.fecha, a.comando, t.codigo as ticket_codigo
        FROM acciones a
        LEFT JOIN tickets t ON a.ticket_id = t.id
        WHERE a.descripcion LIKE ? OR a.comando LIKE ? OR a.resultado LIKE ?
        ORDER BY a.fecha DESC LIMIT ?
    """, (f"%{texto}%",) * 3 + (limite,)).fetchall()

    if acciones:
        results.append("=== ACCIONES ===")
        for a in acciones:
            ref = f" #{a['ticket_codigo']}" if a['ticket_codigo'] else ""
            results.append(f"  [{a['fecha']}] ({a['tipo']}){ref} {a['descripcion']}")
        results.append("")

    conn.close()

    if not results:
        return f"No se encontraron resultados para '{texto}'."

    return "\n".join(results)


# ── Herramientas MCP: ESTADISTICAS ─────────────────────────────────────────

@mcp.tool()
def estadisticas(proyecto: str = "") -> str:
    """Muestra estadisticas numericas de la base de datos.

    Args:
        proyecto: Filtrar por proyecto (opcional, muestra globales si no se indica)
    """
    conn = get_db()

    if proyecto:
        row = conn.execute("SELECT id FROM proyectos WHERE nombre LIKE ?", (f"%{proyecto}%",)).fetchone()
        if not row:
            conn.close()
            return f"Proyecto '{proyecto}' no encontrado."
        pid = row['id']

        stats = {
            'tickets_total': conn.execute("SELECT COUNT(*) FROM tickets WHERE proyecto_id=?", (pid,)).fetchone()[0],
            'tickets_abiertos': conn.execute("SELECT COUNT(*) FROM tickets WHERE proyecto_id=? AND estado IN ('ABIERTO','EN_PROCESO')", (pid,)).fetchone()[0],
            'tickets_cerrados': conn.execute("SELECT COUNT(*) FROM tickets WHERE proyecto_id=? AND estado IN ('RESUELTO','CERRADO')", (pid,)).fetchone()[0],
            'notas': conn.execute("SELECT COUNT(*) FROM notas WHERE proyecto_id=?", (pid,)).fetchone()[0],
            'acciones': conn.execute("SELECT COUNT(*) FROM acciones WHERE proyecto_id=?", (pid,)).fetchone()[0],
            'sesiones': conn.execute("SELECT COUNT(*) FROM sesiones WHERE proyecto_id=?", (pid,)).fetchone()[0],
        }
    else:
        stats = {
            'proyectos': conn.execute("SELECT COUNT(*) FROM proyectos").fetchone()[0],
            'tickets_total': conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0],
            'tickets_abiertos': conn.execute("SELECT COUNT(*) FROM tickets WHERE estado IN ('ABIERTO','EN_PROCESO')").fetchone()[0],
            'tickets_cerrados': conn.execute("SELECT COUNT(*) FROM tickets WHERE estado IN ('RESUELTO','CERRADO')").fetchone()[0],
            'notas': conn.execute("SELECT COUNT(*) FROM notas").fetchone()[0],
            'acciones': conn.execute("SELECT COUNT(*) FROM acciones").fetchone()[0],
            'sesiones': conn.execute("SELECT COUNT(*) FROM sesiones").fetchone()[0],
        }

    conn.close()

    result = [f"=== ESTADISTICAS {('- ' + proyecto) if proyecto else 'GLOBALES'} ==="]
    for k, v in stats.items():
        result.append(f"  {k.replace('_', ' ').title()}: {v}")

    return "\n".join(result)


# ── Inicializacion y arranque ──────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    mcp.run(transport="stdio")
