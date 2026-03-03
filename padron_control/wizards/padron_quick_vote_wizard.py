# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PadronQuickVoteWizard(models.TransientModel):
    _name = 'padron.quick.vote.wizard'
    _description = 'Marcar Voto Rápido'

    # -----------------
    # Defaults / helpers
    # -----------------
    @api.model
    def _default_event(self):
        return self.env['padron.event'].search([('state', '=', 'active')], limit=1)

    @staticmethod
    def _normalize_identifier(value):
        """Normalize input for DNI/Trámite searches."""
        if not value:
            return ''
        value = str(value).strip()
        # Remove common punctuation/spaces.
        for ch in ['.', ',', ' ', '-', '_']:
            value = value.replace(ch, '')
        return value

    @staticmethod
    def _dni_with_dots(value):
        """Return a DNI formatted with dots if it looks like an 7/8-digit DNI."""
        if not value or not value.isdigit():
            return value
        # Common AR DNI formats: 7 or 8 digits
        if len(value) == 8:
            return f"{value[0:2]}.{value[2:5]}.{value[5:8]}"
        if len(value) == 7:
            return f"{value[0:1]}.{value[1:4]}.{value[4:7]}"
        return value

    def _search_person_from_identifier(self, identifier):
        """Return the padron person matching DNI/trámite within user's mesas."""
        identifier = self._normalize_identifier(identifier)
        if not identifier:
            return self.env['res.partner']

        dotted = self._dni_with_dots(identifier)

        domain = [('is_padron_person', '=', True)]

        # Restricción por mesa (si el usuario tiene mesas asignadas).
        # En este módulo la relación está en res.users.mesa_ids.
        # Si no tiene mesas asignadas, no restringimos (comportamiento consistente con res.partner).
        mesa_ids = getattr(self.env.user, 'mesa_ids', self.env['padron.mesa']).ids
        if mesa_ids:
            domain.append(('mesa_id', 'in', mesa_ids))

        domain += ['|', '|',
                   ('dni', '=', identifier),
                   ('dni', '=', dotted),
                   ('tramite', '=', identifier)]

        partners = self.env['res.partner'].search(domain, limit=2)
        if len(partners) > 1:
            # Should not happen, but it's safer to avoid marking the wrong person.
            raise UserError(_("Se encontraron varias personas con ese DNI/Trámite. Ajustá la búsqueda."))
        return partners

    # ------
    # Fields
    # ------
    event_id = fields.Many2one(
        'padron.event',
        string='Evento',
        required=True,
        default=_default_event,
        readonly=True,
    )

    # NOTE:
    # This wizard is meant to work in "modo rápido" (buscar -> marcar -> limpiar).
    # If this field is required at ORM level, clearing it after marking the vote
    # (write({'identifier': False})) will raise a ValidationError and break the
    # workflow. We validate it manually in action_mark_vote.
    identifier = fields.Char(
        string='DNI o Trámite',
        required=False,
        help='Ingresá el DNI (con o sin puntos) o el N° de trámite para buscar la persona.'
    )

    person_id = fields.Many2one(
        'res.partner',
        string='Persona',
        readonly=True,
    )

    mesa_id = fields.Many2one(
        'padron.mesa',
        string='Mesa N°',
        related='person_id.mesa_id',
        readonly=True,
    )

    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehículo (opcional)',
        related='person_id.vehicle_id',
        readonly=True,
    )

    vote_status = fields.Selection(
        [('voted', 'Votó'), ('not_voted', 'No votó')],
        string='Estado',
        compute='_compute_vote_status',
        readonly=True,
    )

    @api.depends('person_id', 'person_id.padron_vote_state')
    def _compute_vote_status(self):
        for w in self:
            state = (w.person_id.padron_vote_state or 'not_voted') if w.person_id else 'not_voted'
            w.vote_status = 'voted' if state == 'voted' else 'not_voted'

    # ---------
    # Onchange
    # ---------
    @api.onchange('identifier')
    def _onchange_identifier(self):
        """Fill the person based on DNI/trámite. Don't block typing with hard errors."""
        self.person_id = False
        if not self.identifier:
            return

        try:
            person = self._search_person_from_identifier(self.identifier)
        except UserError:
            # Keep it silent while typing; action_mark will show a clear message.
            return

        self.person_id = person[:1] if person else False

    # ---------
    # Actions
    # ---------
    def action_mark(self):
        self.ensure_one()

        identifier = self._normalize_identifier(self.identifier)
        if not identifier:
            raise UserError(_("Ingresá un DNI o N° de trámite."))

        person = self.person_id
        if not person:
            person = self._search_person_from_identifier(identifier)
            person = person[:1] if person else self.env['res.partner']

        if not person:
            raise UserError(_("No se encontró ninguna persona con ese DNI/Trámite."))

        # Enforce mesa restrictions.
        person._padron_assert_user_mesa_access()

        if not self.event_id:
            raise UserError(_("No hay un evento activo para registrar el voto."))

        now = fields.Datetime.now()

        # 1) Update partner state (used by list view / counters)
        person.write({
            'padron_vote_state': 'voted',
            'padron_vote_datetime': now,
            'padron_vote_user_id': self.env.user.id,
        })

        # 2) Upsert check-in (history)
        Checkin = self.env['padron.checkin']
        existing = Checkin.search([
            ('event_id', '=', self.event_id.id),
            ('person_id', '=', person.id),
        ], order='id desc', limit=1)

        vals = {
            'event_id': self.event_id.id,
            'person_id': person.id,
            'vote_status': 'voted',
            'user_id': self.env.user.id,
            'checkin_datetime': now,
            'vehicle_id': person.vehicle_id.id or False,
        }
        if existing:
            existing.write(vals)
        else:
            Checkin.create(vals)

        # Reset for next scan/input
        self.identifier = False
        self.person_id = False

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Marcar Voto (Rápido)'),
            'context': {'default_event_id': self.event_id.id},
        }

    def action_clear(self):
        self.ensure_one()
        self.identifier = False
        self.person_id = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Marcar Voto (Rápido)'),
            'context': {'default_event_id': self.event_id.id if self.event_id else False},
        }
