# -*- coding: utf-8 -*-
{
    'name': 'Payment Register Statement - Argentina',
    'version': '19.0.1.0.0',
    'summary': 'Estado correcto de cheques de terceros y transferencias cross-company',
    'description': """
Módulo glue que integra payment_register_statement_v19 con l10n_latam_check.

Problema que resuelve
---------------------
El filtro nativo "A la mano" (issue_state = 'handed') nunca muestra cheques de
terceros porque issue_state solo se calcula para cheques propios. Este módulo
agrega un campo prs_third_party_state con lógica correcta para third-party:

  * En cartera: el cheque está en un diario de tipo caja/cash (disponible físicamente)
  * Depositado: el cheque está en un diario de tipo banco
  * Entregado/Endosado: el cheque salió de todos los diarios (fue entregado a un tercero)

También agrega prs_endorsed_to_id para saber a quién fue entregado.

Filtros
-------
Reemplaza el filtro nativo "On hand" / "Handed" por tres filtros PRS que
funcionan con el campo nuevo. El filtro "En cartera" queda activo por defecto
al abrir la vista de Cheques de Terceros.
    """,
    'author': 'Alderete IS',
    'category': 'Accounting',
    'license': 'LGPL-3',

    'depends': [
        'payment_register_statement_v19',
        'l10n_latam_check',
    ],

    'data': [
        'views/account_journal_check_views.xml',
        'views/prs_third_party_check_view.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}
