# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """
    Migración al instalar:
    1. Lee company_id de cada contacto y sube hasta la empresa raíz.
    2. Inserta esa empresa raíz en allowed_company_ids (tabla M2M).
    3. Clasifica contactos de empresas y usuarios internos para ocultarlos del uso comercial.
    4. Pone company_id = NULL en todos los contactos.
    """
    # 1. Obtener el mapeo empresa -> empresa raíz usando SQL recursivo.
    #    Para cada empresa, recorre sus padres hasta encontrar parent_id IS NULL.
    env.cr.execute("""
        WITH RECURSIVE company_tree AS (
            SELECT id AS company_id, id AS root_id, parent_id
            FROM res_company
            UNION ALL
            SELECT ct.company_id, parent.id AS root_id, parent.parent_id
            FROM company_tree ct
            JOIN res_company parent ON parent.id = ct.parent_id
        )
        SELECT company_id, root_id
        FROM company_tree
        WHERE parent_id IS NULL
    """)
    company_to_root = {row[0]: row[1] for row in env.cr.fetchall()}

    # 2. Leer qué empresa tenía cada contacto
    env.cr.execute("""
        SELECT id, company_id
        FROM res_partner
        WHERE company_id IS NOT NULL
    """)
    rows = env.cr.fetchall()

    # 3. Insertar en la tabla M2M la empresa raíz correspondiente
    if rows:
        rel_table = "mcc_res_partner_allowed_company_rel"
        values = []
        for partner_id, company_id in rows:
            root_id = company_to_root.get(company_id, company_id)
            values.append((partner_id, root_id))

        env.cr.executemany(
            f"INSERT INTO {rel_table} (partner_id, company_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            values,
        )

    # 4. Clasificar contactos críticos del sistema antes de limpiar company_id.
    env["res.partner"]._mcc_auto_configure_system_contacts()

    # 5. Limpiar company_id nativo
    env.cr.execute("UPDATE res_partner SET company_id = NULL WHERE company_id IS NOT NULL")


def uninstall_hook(env):
    """
    Al desinstalar: restaura company_id tomando la primera empresa
    asignada en allowed_company_ids (ordenada por id).
    """
    env.cr.execute("""
        UPDATE res_partner p
        SET company_id = (
            SELECT rel.company_id
            FROM mcc_res_partner_allowed_company_rel rel
            WHERE rel.partner_id = p.id
            ORDER BY rel.company_id
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM mcc_res_partner_allowed_company_rel rel
            WHERE rel.partner_id = p.id
        )
    """)
