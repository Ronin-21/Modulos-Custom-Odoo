# -*- coding: utf-8 -*-
from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)


MCC_USAGE_FIELDS = {
    "pos": "mcc_available_pos",
    "sale": "mcc_available_sale",
    "purchase": "mcc_available_purchase",
    "accounting": "mcc_available_accounting",
}

MCC_EFFECTIVE_USAGE_FIELDS = {
    "pos": "mcc_effective_pos_available",
    "sale": "mcc_effective_sale_available",
    "purchase": "mcc_effective_purchase_available",
    "accounting": "mcc_effective_accounting_available",
}

MCC_USAGE_CONFIG_FIELDS = {
    "mcc_contact_usage_type",
    "mcc_hide_business_operations",
    "mcc_available_pos",
    "mcc_available_sale",
    "mcc_available_purchase",
    "mcc_available_accounting",
}


def _remove_nodes(nodes):
    for n in nodes:
        p = n.getparent()
        if p is not None:
            p.remove(n)


class ResPartner(models.Model):
    _inherit = "res.partner"

    allowed_company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="mcc_res_partner_allowed_company_rel",
        column1="partner_id",
        column2="company_id",
        string="Empresas permitidas",
        domain=lambda self: [("id", "in", self.env.companies.ids)],
        default=lambda self: self._mc_default_allowed_companies_rs(),
        help=(
            "Obligatorio. Define en qué empresas (del selector) será visible/usable este contacto. "
            "Solo se pueden asignar empresas que estén seleccionadas en el selector multi-empresa."
        ),
    )

    # -------------------------------------------------------------------------
    # Uso comercial / contactos del sistema
    # -------------------------------------------------------------------------
    mcc_contact_usage_type = fields.Selection(
        selection=[
            ("commercial", "Comercial / Cliente-Proveedor"),
            ("company_branch", "Empresa / Sucursal del sistema"),
            ("system_user", "Usuario del sistema"),
            ("system_admin", "Administrador del sistema"),
        ],
        string="Tipo de contacto",
        default="commercial",
        required=True,
        index=True,
        help=(
            "Clasificación operativa del contacto. Al cambiar el tipo se cargan presets "
            "por defecto. La restricción final la definen el bloqueo general y los checks."
        ),
    )
    mcc_hide_business_operations = fields.Boolean(
        string="Ocultar en operaciones comerciales",
        default=False,
        index=True,
        help=(
            "Bloqueo general absoluto. Si está activo, el contacto no puede usarse en POS, "
            "Ventas, Compras ni Contabilidad y los checks de disponibilidad quedan apagados."
        ),
    )
    mcc_available_pos = fields.Boolean(string="Disponible en POS", default=True, index=True)
    mcc_available_sale = fields.Boolean(string="Disponible en Ventas", default=True, index=True)
    mcc_available_purchase = fields.Boolean(string="Disponible en Compras", default=True, index=True)
    mcc_available_accounting = fields.Boolean(string="Disponible en Contabilidad", default=True, index=True)

    mcc_is_system_contact = fields.Boolean(
        string="Contacto del sistema",
        compute="_compute_mcc_effective_business_flags",
        store=True,
        index=True,
        help="Campo técnico/informativo: identifica empresas, sucursales, usuarios o administradores del sistema.",
    )
    mcc_effective_hide_business_operations = fields.Boolean(
        string="Oculto comercial efectivo",
        compute="_compute_mcc_effective_business_flags",
        store=True,
        index=True,
        help="Campo técnico: considera también la empresa/contacto comercial padre.",
    )
    mcc_effective_pos_available = fields.Boolean(
        string="Disponible efectivo POS",
        compute="_compute_mcc_effective_business_flags",
        store=True,
        index=True,
    )
    mcc_effective_sale_available = fields.Boolean(
        string="Disponible efectivo Ventas",
        compute="_compute_mcc_effective_business_flags",
        store=True,
        index=True,
    )
    mcc_effective_purchase_available = fields.Boolean(
        string="Disponible efectivo Compras",
        compute="_compute_mcc_effective_business_flags",
        store=True,
        index=True,
    )
    mcc_effective_accounting_available = fields.Boolean(
        string="Disponible efectivo Contabilidad",
        compute="_compute_mcc_effective_business_flags",
        store=True,
        index=True,
    )

    mcc_current_user_can_manage_usage = fields.Boolean(
        string="Puede administrar uso comercial",
        compute="_compute_mcc_current_user_can_manage_usage",
        help="Campo técnico para mostrar/ocultar el bloque Uso comercial según el permiso del usuario actual.",
    )

    def _compute_mcc_current_user_can_manage_usage(self):
        can_manage = bool(
            hasattr(self.env.user, "mcc_can_manage_business_contact_usage")
            and self.env.user.mcc_can_manage_business_contact_usage()
        )
        for partner in self:
            partner.mcc_current_user_can_manage_usage = can_manage

    @api.depends(
        "commercial_partner_id",
        "mcc_contact_usage_type",
        "mcc_hide_business_operations",
        "mcc_available_pos",
        "mcc_available_sale",
        "mcc_available_purchase",
        "mcc_available_accounting",
        "commercial_partner_id.mcc_contact_usage_type",
        "commercial_partner_id.mcc_hide_business_operations",
        "commercial_partner_id.mcc_available_pos",
        "commercial_partner_id.mcc_available_sale",
        "commercial_partner_id.mcc_available_purchase",
        "commercial_partner_id.mcc_available_accounting",
    )
    def _compute_mcc_effective_business_flags(self):
        system_types = {"company_branch", "system_user", "system_admin"}
        for partner in self:
            commercial = partner.commercial_partner_id or partner
            source = commercial if commercial and commercial != partner else partner

            # Regla funcional vigente:
            # - El tipo de contacto es clasificación + presets por defecto.
            # - "Ocultar en operaciones comerciales" es bloqueo absoluto.
            # - Los checks Disponible en POS/Ventas/Compras/Contabilidad definen cada flujo.
            # - Esto aplica para TODOS los usuarios, incluidos administradores.
            # - El permiso del usuario solo permite ver/editar estos checks; no otorga bypass.
            is_system = partner.mcc_contact_usage_type in system_types or source.mcc_contact_usage_type in system_types
            hidden = bool(partner.mcc_hide_business_operations or source.mcc_hide_business_operations)

            pos_available = bool(not hidden and partner.mcc_available_pos and source.mcc_available_pos)
            sale_available = bool(not hidden and partner.mcc_available_sale and source.mcc_available_sale)
            purchase_available = bool(not hidden and partner.mcc_available_purchase and source.mcc_available_purchase)
            accounting_available = bool(not hidden and partner.mcc_available_accounting and source.mcc_available_accounting)

            partner.mcc_is_system_contact = is_system
            partner.mcc_effective_pos_available = pos_available
            partner.mcc_effective_sale_available = sale_available
            partner.mcc_effective_purchase_available = purchase_available
            partner.mcc_effective_accounting_available = accounting_available
            partner.mcc_effective_hide_business_operations = bool(
                hidden or not (pos_available or sale_available or purchase_available or accounting_available)
            )

    # ----------------------------
    # Helpers M2M
    # ----------------------------
    def _mc_apply_m2m_commands(self, initial_ids, commands):
        ids = set(initial_ids or [])
        if not commands:
            return ids
        if not isinstance(commands, list):
            raise UserError(_("Formato inválido para 'Empresas permitidas'."))

        for cmd in commands:
            if not isinstance(cmd, (list, tuple)) or not cmd:
                continue
            op = cmd[0]
            if op == 6:
                ids = set(cmd[2] or [])
            elif op == 5:
                ids = set()
            elif op == 4:
                ids.add(cmd[1])
            elif op == 3:
                ids.discard(cmd[1])
            elif op in (0, 1, 2):
                # Crear/actualizar/eliminar empresas desde un contacto no tiene sentido;
                # se ignoran estos comandos de forma segura.
                _logger.warning(
                    "mcc: comando ORM %s ignorado en allowed_company_ids (no aplicable a res.company).",
                    op,
                )
        return ids

    def _mc_validate_allowed_companies(self, company_ids_set):
        ids = set(company_ids_set or [])
        if not ids:
            raise UserError(_("Debe indicar al menos una empresa en 'Empresas permitidas'."))

        allowed_in_context = set(self.env.companies.ids)
        if not ids.issubset(allowed_in_context):
            bad_ids = sorted(list(ids - allowed_in_context))
            bad_names = self.env["res.company"].browse(bad_ids).mapped("display_name")
            raise UserError(_(
                "Solo puede asignar empresas que estén tildadas en el selector multi-empresa. "
                "Empresas no permitidas: %s"
            ) % (", ".join(bad_names) or str(bad_ids)))

        # La empresa activa es solo un DEFAULT/sugerencia al crear.
        # No se fuerza al guardar, porque el usuario debe poder cambiar
        # manualmente las Empresas permitidas mientras no quede vacío.
        return ids

    def _mc_get_root_company(self, company):
        """Devuelve la empresa raíz (matriz) siguiendo parent_id."""
        root = company
        while root.parent_id:
            root = root.parent_id
        return root

    @api.model
    def _mc_default_allowed_companies_rs(self):
        """Default para 'Empresas permitidas': solo la empresa activa.

        Es una sugerencia inicial para que el campo nunca nazca vacío.
        Luego el usuario puede cambiarlo manualmente por otra empresa permitida
        del selector multiempresa. Si el contacto se crea como hijo de otro
        contacto, el create() conserva la herencia desde el padre.
        """
        return self.env.company

    # -------------------------------------------------------------------------
    # Helpers de uso comercial
    # -------------------------------------------------------------------------
    @api.model
    def _mcc_business_admin_allowed(self, usage=None):
        """No hay bypass por usuario o administrador.

        Los checks del contacto aplican para todos los usuarios. El permiso en
        res.users solo permite ver/editar la configuración de Uso comercial, no
        usar contactos del sistema en operaciones.
        """
        return False

    @api.model
    def _mcc_usage_type_defaults(self, usage_type):
        """Presets funcionales según el tipo de contacto.

        El tipo clasifica y propone configuración. El bloqueo final sigue estando
        en Ocultar en operaciones comerciales + checks de disponibilidad.
        """
        if usage_type in ("company_branch", "system_user", "system_admin"):
            return {
                "mcc_hide_business_operations": True,
                "mcc_available_pos": False,
                "mcc_available_sale": False,
                "mcc_available_purchase": False,
                "mcc_available_accounting": False,
            }
        return {
            "mcc_hide_business_operations": False,
            "mcc_available_pos": True,
            "mcc_available_sale": True,
            "mcc_available_purchase": True,
            "mcc_available_accounting": True,
        }

    @api.model
    def _mcc_apply_usage_type_defaults_to_vals(self, vals):
        if "mcc_contact_usage_type" in vals:
            usage_type = vals.get("mcc_contact_usage_type") or "commercial"
            vals.update(self._mcc_usage_type_defaults(usage_type))
        return vals

    @api.model
    def _mcc_enforce_hide_business_vals(self, vals, records=None):
        """Garantiza que el bloqueo general sea absoluto.

        Si el bloqueo está activo, no se permite dejar checks operativos activos.
        Si un registro ya está bloqueado y se intenta activar un check sin desactivar
        el bloqueo en la misma operación, se informa al usuario.
        """
        availability_fields = (
            "mcc_available_pos",
            "mcc_available_sale",
            "mcc_available_purchase",
            "mcc_available_accounting",
        )
        if vals.get("mcc_hide_business_operations") is True:
            for field_name in availability_fields:
                vals[field_name] = False
            return vals

        if records and "mcc_hide_business_operations" not in vals:
            wants_enable = any(vals.get(field_name) is True for field_name in availability_fields)
            if wants_enable and records.filtered("mcc_hide_business_operations"):
                raise UserError(_(
                    "Debe desactivar primero 'Ocultar en operaciones comerciales' antes de habilitar "
                    "POS, Ventas, Compras o Contabilidad."
                ))
        return vals

    @api.onchange("mcc_contact_usage_type")
    def _onchange_mcc_contact_usage_type(self):
        for partner in self:
            defaults = partner._mcc_usage_type_defaults(partner.mcc_contact_usage_type or "commercial")
            for field_name, value in defaults.items():
                partner[field_name] = value

    @api.onchange("mcc_hide_business_operations")
    def _onchange_mcc_hide_business_operations(self):
        for partner in self:
            if partner.mcc_hide_business_operations:
                partner.mcc_available_pos = False
                partner.mcc_available_sale = False
                partner.mcc_available_purchase = False
                partner.mcc_available_accounting = False

    @api.model
    def _mcc_business_domain(self, usage):
        """Dominio reutilizable para campos partner_id de operaciones comerciales."""
        if self._mcc_business_admin_allowed(usage):
            return []
        field_name = MCC_EFFECTIVE_USAGE_FIELDS.get(usage)
        if not field_name:
            return [("mcc_effective_hide_business_operations", "=", False)]
        return [(field_name, "=", True)]

    def _mcc_is_blocked_for_usage(self, usage):
        self.ensure_one()
        if self._mcc_business_admin_allowed(usage):
            return False
        effective_field = MCC_EFFECTIVE_USAGE_FIELDS.get(usage)
        if effective_field:
            return not bool(self[effective_field])
        return bool(self.mcc_effective_hide_business_operations)

    @api.model
    def _mcc_skip_business_usage_validation(self):
        """Contexto técnico para flujos internos del sistema.

        No es un bypass de usuario. Se usa para procesos automáticos donde Odoo
        necesita crear asientos/pagos internos, por ejemplo el cierre de una
        sesión POS, aunque el partner de la sucursal/compañía esté bloqueado
        para selección comercial manual.
        """
        ctx = self.env.context
        return bool(
            ctx.get("mcc_skip_business_usage_validation")
            or ctx.get("mcc_skip_accounting_business_usage_validation")
        )

    def _mcc_check_business_usage(self, usage, document_label=None):
        """Valida que los contactos del recordset puedan usarse en el flujo indicado."""
        if self._mcc_skip_business_usage_validation():
            return True
        if self._mcc_business_admin_allowed(usage):
            return True
        blocked = self.filtered(lambda p: p._mcc_is_blocked_for_usage(usage))
        if blocked:
            names = ", ".join(blocked[:5].mapped("display_name"))
            more = "..." if len(blocked) > 5 else ""
            usage_label = {
                "pos": "POS",
                "sale": "Ventas",
                "purchase": "Compras",
                "accounting": "Contabilidad",
            }.get(usage, usage or "operaciones comerciales")
            raise UserError(_(
                "El contacto '%(contact)s%(more)s' no está disponible para %(usage)s.\n\n"
                "Revise 'Ocultar en operaciones comerciales' y los checks de disponibilidad del contacto."
            ) % {
                "contact": names,
                "more": more,
                "usage": document_label or usage_label,
            })
        return True

    @api.model
    def _mcc_auto_configure_system_contacts(self):
        """
        Clasifica automáticamente contactos críticos del sistema.
        Se ejecuta al instalar/actualizar el módulo desde XML y también desde post_init_hook.
        """
        all_companies = self.env["res.company"].sudo().search([])
        all_company_ids = all_companies.ids
        ctx = dict(self.env.context, mcc_skip_allowed_company_validation=True)
        Partner = self.sudo().with_context(ctx).with_context(allowed_company_ids=all_company_ids or [self.env.company.id])

        def _system_contact_vals(partner, usage_type):
            """Clasifica contactos del sistema sin pisar ajustes manuales ya hechos.

            Si el contacto todavía estaba como "commercial" lo bloqueamos por defecto
            al clasificarlo como sistema. Si ya estaba clasificado como contacto del
            sistema, preservamos los checks manuales del usuario.
            """
            vals = {
                "mcc_contact_usage_type": usage_type,
                # Importante: dejarlos visibles para todas las empresas a nivel sistema.
                "allowed_company_ids": [(6, 0, all_company_ids)],
                "company_id": False,
            }
            if partner.mcc_contact_usage_type == "commercial":
                vals.update({
                    "mcc_hide_business_operations": True,
                    "mcc_available_pos": False,
                    "mcc_available_sale": False,
                    "mcc_available_purchase": False,
                    "mcc_available_accounting": False,
                })
            return vals

        # Contactos vinculados a empresas/sucursales del sistema.
        company_partners = all_companies.mapped("partner_id").exists()
        for partner in company_partners:
            partner.with_context(ctx).sudo().write(_system_contact_vals(partner, "company_branch"))

        # Contactos vinculados a usuarios internos. No se marcan usuarios portal/cliente.
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        try:
            internal_users = Users.search([("share", "=", False), ("partner_id", "!=", False)])
        except Exception:
            internal_users = Users.search([("partner_id", "!=", False)])

        group_system = self.env.ref("base.group_system", raise_if_not_found=False)
        admin_users = internal_users.filtered(lambda u: group_system and group_system in u.groups_id)
        normal_users = internal_users - admin_users

        admin_partners = admin_users.mapped("partner_id").exists()
        user_partners = normal_users.mapped("partner_id").exists()

        for partner in user_partners:
            partner.with_context(ctx).sudo().write(_system_contact_vals(partner, "system_user"))
        for partner in admin_partners:
            partner.with_context(ctx).sudo().write(_system_contact_vals(partner, "system_admin"))

        # Forzar recálculo de campos efectivos después de una actualización de módulo.
        # Es clave cuando cambia la fórmula de cálculo pero los campos store=True
        # conservan valores anteriores.
        (company_partners | user_partners | admin_partners).sudo()._compute_mcc_effective_business_flags()

        _logger.info(
            "mcc: contactos del sistema clasificados. empresas=%s usuarios=%s admins=%s",
            len(company_partners), len(user_partners), len(admin_partners),
        )
        return True

    @api.model
    def _mcc_normalize_legacy_usage_types(self):
        """Convierte valores legacy retirados del selector.

        La opción 'Interno / Técnico' fue eliminada del campo seleccionable para
        simplificar la operación. Los registros existentes con valor 'internal'
        se reclasifican como 'Usuario del sistema' y quedan bloqueados por defecto.
        """
        legacy = self.sudo().with_context(active_test=False, mcc_skip_allowed_company_validation=True).search([
            ("mcc_contact_usage_type", "=", "internal")
        ])
        if legacy:
            legacy.write({
                "mcc_contact_usage_type": "system_user",
                "mcc_hide_business_operations": True,
                "mcc_available_pos": False,
                "mcc_available_sale": False,
                "mcc_available_purchase": False,
                "mcc_available_accounting": False,
            })
        _logger.info("mcc: tipos legacy 'internal' normalizados: %s", len(legacy))
        return True

    @api.model
    def _mcc_recompute_all_business_flags(self):
        """Recalcula campos efectivos de uso comercial en actualización."""
        partners = self.sudo().with_context(active_test=False).search([])
        partners._compute_mcc_effective_business_flags()
        _logger.info("mcc: campos efectivos de uso comercial recalculados para %s contactos", len(partners))
        return True

    @api.model
    def _mcc_current_user_can_manage_usage_config(self):
        return bool(
            hasattr(self.env.user, "mcc_can_manage_business_contact_usage")
            and self.env.user.mcc_can_manage_business_contact_usage()
        )

    @api.model
    def _mcc_filter_contacts_app_visibility(self):
        """Indica si la vista general de Contactos debe ocultar contactos internos/sistema.

        La restricción se activa solo en acciones de Contactos marcadas con contexto
        ``mcc_contacts_app_visibility``. No se implementa como ir.rule para evitar
        romper lecturas internas de Odoo, cierres POS, asientos, usuarios o compañías.

        El mismo check del usuario ``Administrar uso comercial de contactos`` permite
        ver/administrar esos contactos en la app Contactos.
        """
        return bool(
            self.env.context.get("mcc_contacts_app_visibility")
            and not self._mcc_current_user_can_manage_usage_config()
        )

    @api.model
    def _mcc_contacts_app_visibility_domain(self):
        """Dominio de visibilidad para usuarios sin permiso de administración comercial.

        En la app Contactos, esos usuarios solo ven contactos comerciales operativos.
        Se ocultan:
        - Empresas / sucursales del sistema.
        - Usuarios del sistema.
        - Administradores del sistema.
        - Contactos ocultos o sin disponibilidad comercial efectiva.
        """
        return [
            ("mcc_is_system_contact", "=", False),
            ("mcc_effective_hide_business_operations", "=", False),
        ]

    @api.model
    def _mcc_apply_contacts_app_visibility_domain(self, domain):
        domain = list(domain or [])
        if self._mcc_filter_contacts_app_visibility():
            return expression.AND([domain, self._mcc_contacts_app_visibility_domain()])
        return domain

    @api.model
    def _mcc_configure_contacts_app_actions(self):
        """Marca acciones principales de Contactos con contexto de visibilidad.

        Se ejecuta al instalar/actualizar. El contexto activa un filtro en search_read
        y web_search_read: los usuarios sin el check en res.users no ven contactos
        internos/sistema en la app Contactos, pero Odoo puede seguir leyéndolos
        internamente por otros flujos técnicos.
        """
        xmlids = [
            "base.action_partner_form",
            "contacts.action_contacts",
        ]
        updated = 0
        for xmlid in xmlids:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if not action or action._name != "ir.actions.act_window":
                continue
            ctx = {}
            if action.context:
                try:
                    ctx = safe_eval(action.context) if isinstance(action.context, str) else dict(action.context)
                except Exception:
                    _logger.warning("mcc: no se pudo evaluar el contexto de la acción %s: %s", xmlid, action.context)
                    ctx = {}
            ctx["mcc_contacts_app_visibility"] = True
            action.sudo().write({"context": repr(ctx)})
            updated += 1
        _logger.info("mcc: acciones de Contactos configuradas con visibilidad por usuario: %s", updated)
        return True

    @api.model
    def _mcc_force_commercial_defaults(self, vals):
        vals.setdefault("mcc_contact_usage_type", "commercial")
        vals.setdefault("mcc_hide_business_operations", False)
        vals.setdefault("mcc_available_pos", True)
        vals.setdefault("mcc_available_sale", True)
        vals.setdefault("mcc_available_purchase", True)
        vals.setdefault("mcc_available_accounting", True)
        return vals

    @api.model
    def _mcc_sanitize_usage_vals_for_non_manager_create(self, vals):
        """Al crear contactos sin permiso de administración, fuerza uso comercial."""
        if self._mcc_current_user_can_manage_usage_config():
            return vals
        clean = dict(vals)
        for key in MCC_USAGE_CONFIG_FIELDS:
            clean.pop(key, None)
        return self._mcc_force_commercial_defaults(clean)

    @api.model
    def _mcc_check_usage_write_permission(self, vals):
        if self.env.context.get("mcc_skip_allowed_company_validation"):
            return True
        if MCC_USAGE_CONFIG_FIELDS.intersection(vals.keys()) and not self._mcc_current_user_can_manage_usage_config():
            raise UserError(_(
                "No tiene permiso para modificar el bloque 'Uso comercial' del contacto. "
                "Solicite a un usuario habilitado para administrar uso comercial de contactos."
            ))
        return True

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Refuerzo para Many2one en operaciones comerciales.

        Algunas vistas o módulos pueden alterar dominios en los campos partner_id.
        Si el contexto indica el uso comercial, siempre agregamos el dominio efectivo.
        """
        args = self._mcc_apply_contacts_app_visibility_domain(args or [])
        usage = self.env.context.get("mcc_business_usage")
        if usage in MCC_EFFECTIVE_USAGE_FIELDS:
            args = expression.AND([args, self._mcc_business_domain(usage)])
        return super().name_search(name=name, args=args, operator=operator, limit=limit)

    # ----------------------------
    # CRUD
    # ----------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("mcc_skip_allowed_company_validation"):
            for vals in vals_list:
                vals["company_id"] = False
            return super().create(vals_list)

        for index, vals in enumerate(vals_list):
            vals = self._mcc_sanitize_usage_vals_for_non_manager_create(dict(vals))
            vals_list[index] = vals
            vals["company_id"] = False

            # El tipo de contacto trae la configuración por defecto.
            # Si no se indicó tipo, se crea como contacto comercial.
            if "mcc_contact_usage_type" in vals:
                self._mcc_apply_usage_type_defaults_to_vals(vals)
            else:
                self._mcc_force_commercial_defaults(vals)
            self._mcc_enforce_hide_business_vals(vals)

            if "allowed_company_ids" not in vals:
                parent_id = vals.get("parent_id")
                if parent_id:
                    parent = self.env["res.partner"].browse(parent_id).exists()
                    parent_companies = parent.allowed_company_ids & self.env.companies
                    source = parent_companies if parent_companies else self._mc_default_allowed_companies_rs()
                else:
                    source = self._mc_default_allowed_companies_rs()
                vals["allowed_company_ids"] = [(6, 0, source.ids)]

            final_ids = self._mc_apply_m2m_commands(set(), vals.get("allowed_company_ids"))
            final_ids = self._mc_validate_allowed_companies(final_ids)
            vals["allowed_company_ids"] = [(6, 0, list(final_ids))]

        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("mcc_skip_allowed_company_validation"):
            vals = dict(vals)
            vals["company_id"] = False
            return super().write(vals)

        vals = dict(vals)
        self._mcc_check_usage_write_permission(vals)

        # Forzar company_id siempre vacío si alguien lo pasa explícitamente
        if vals.get("company_id") not in (False, None):
            vals["company_id"] = False

        # El tipo de contacto trae la configuración por defecto.
        self._mcc_apply_usage_type_defaults_to_vals(vals)
        self._mcc_enforce_hide_business_vals(vals, records=self)

        if "allowed_company_ids" not in vals:
            # No se está tocando allowed_company_ids: dejamos pasar sin bloquear.
            # Los registros legacy (sin empresas) son cubiertos por la ir.rule
            # que los muestra a todos hasta que el usuario los complete.
            vals["company_id"] = False
            return super().write(vals)

        commands = vals.get("allowed_company_ids")

        # Escribir el resto de campos en un solo super().write() (batch)
        other_vals = {k: v for k, v in vals.items() if k not in ("allowed_company_ids", "company_id")}
        other_vals["company_id"] = False
        if other_vals:
            super().write(other_vals)

        # Agrupar registros por resultado final para minimizar escrituras
        grouped = {}
        for rec in self:
            start_ids = set(rec.allowed_company_ids.ids)
            final_ids = rec._mc_apply_m2m_commands(start_ids, commands)
            final_ids = rec._mc_validate_allowed_companies(final_ids)
            key = frozenset(final_ids)
            grouped.setdefault(key, []).append(rec.id)

        for final_ids_set, rec_ids in grouped.items():
            super(ResPartner, self.browse(rec_ids)).write({
                "allowed_company_ids": [(6, 0, list(final_ids_set))],
                "company_id": False,
            })

        return True

    # ------------------------------------------------------------
    # Search panel: fix TypeError en allowed_company_ids
    # ------------------------------------------------------------
    def _search_panel_domain_image(self, field_name, domain, set_count=False, limit=False):
        """
        Odoo llama a este método para construir las opciones del search panel.
        Cuando agrupa por un campo Many2many, puede encontrar grupos donde el valor
        del campo es False (contactos sin empresas asignadas) e intenta desempaquetarlo
        como (id, nombre), generando: TypeError: cannot unpack non-iterable bool object.

        La solución es excluir esos registros del dominio antes de llamar al super(),
        de modo que el panel solo muestre grupos con valor real.
        """
        domain = self._mcc_apply_contacts_app_visibility_domain(domain or [])
        if field_name == "allowed_company_ids":
            domain = expression.AND([domain, [(field_name, "!=", False)]])
        return super()._search_panel_domain_image(
            field_name, domain, set_count=set_count, limit=limit
        )

    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # POS data loader/search helpers.
    # ------------------------------------------------------------
    @api.model
    def _load_pos_data_domain(self, data):
        domain = super()._load_pos_data_domain(data) if hasattr(super(), "_load_pos_data_domain") else []
        pos_domain = self._mcc_business_domain("pos")

        # Odoo carga el partner del usuario conectado para resolver relaciones internas.
        # Lo mantenemos disponible técnicamente, pero el JS del POS lo filtra para que
        # no aparezca como cliente seleccionable.
        current_user_partner_domain = [("id", "=", self.env.user.partner_id.id)]
        return expression.OR([
            current_user_partner_domain,
            expression.AND([domain, pos_domain]),
        ])

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id) if hasattr(super(), "_load_pos_data_fields") else []
        extra_fields = [
            "mcc_contact_usage_type",
            "mcc_hide_business_operations",
            "mcc_effective_hide_business_operations",
            "mcc_effective_pos_available",
        ]
        for field_name in extra_fields:
            if field_name not in fields_list:
                fields_list.append(field_name)
        return fields_list

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **kwargs):
        """Mantener compatibilidad con Odoo 18 POS loader.

        El POS llama a search_read(..., load=False). Si el override no acepta
        kwargs, el punto de venta falla al cargar con:
        "got an unexpected keyword argument 'load'".
        """
        domain = self._mcc_apply_contacts_app_visibility_domain(domain or [])
        if self.env.context.get("mcc_pos_force_filter"):
            domain = expression.AND([domain or [], self._mcc_business_domain("pos")])
        return super().search_read(
            domain=domain,
            fields=fields,
            offset=offset,
            limit=limit,
            order=order,
            **kwargs,
        )

    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None):
        """Filtro de la app Contactos en las vistas modernas del backend.

        Odoo web usa web_search_read para list/kanban. Aplicamos el filtro solo
        si la acción trae el contexto mcc_contacts_app_visibility.
        """
        domain = self._mcc_apply_contacts_app_visibility_domain(domain or [])
        return super().web_search_read(
            domain=domain,
            specification=specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )

    # Ocultar company_id del FORM en runtime
    # Odoo 18: se usa _get_view en lugar del deprecado fields_view_get
    # ------------------------------------------------------------
    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)

        if view_type == "form" and arch is not None:
            try:
                _remove_nodes(arch.xpath("//field[@name='company_id']"))
                _remove_nodes(arch.xpath("//label[@for='company_id']"))
                _remove_nodes(arch.xpath(
                    "//label[@string='Company'] | //label[@string='Empresa']"
                ))
                _remove_nodes(arch.xpath(
                    "//separator[@string='Company'] | //separator[@string='Empresa']"
                ))
            except Exception:
                pass

        return arch, view
