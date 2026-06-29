import { Component, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { Domain } from "@web/core/domain";
import { TreeEditorBits } from "../tree_editor/tree_editor";
import {
    domainFromTree,
    treeFromDomain,
    formatValue,
    condition,
} from "../tree_editor/condition_tree";
import { useLoadFieldInfo } from "../model_field_selector/utils";
import { CheckBox } from "@web/core/checkbox/checkbox";
import { deepEqual } from "@web/core/utils/objects";
import { getDomainDisplayedOperators } from "./domain_selector_operator_editor";
import { getOperatorEditorInfo } from "../tree_editor/tree_editor_operator_editor";
import { _t } from "@web/core/l10n/translation";
import { ModelFieldSelectorBits } from "../model_field_selector/model_field_selector";
import { useService } from "@web/core/utils/hooks";
import { useMakeGetFieldDef } from "../tree_editor/utils";
import { getDefaultCondition } from "./utils";

const ARCHIVED_CONDITION = condition("active", "in", [true, false]);
const ARCHIVED_DOMAIN = `[("active", "in", [True, False])]`;

const COMPANY_CONDITION_FALSE = condition("company_id", "=", false);
const COMPANY_CONDITION_IN = condition("company_id", "in", [0]);

export class DomainSelectorBits extends Component {
    static template = "awdw.DomainSelectorBits";
    static components = { TreeEditorBits, CheckBox };
    static props = {
        domain: String,
        resModel: String,
        className: { type: String, optional: true },
        defaultConnector: { type: [{ value: "&" }, { value: "|" }], optional: true },
        isDebugMode: { type: Boolean, optional: true },
        readonly: { type: Boolean, optional: true },
        update: { type: Function, optional: true },
        debugUpdate: { type: Function, optional: true },
    };
    static defaultProps = {
        isDebugMode: false,
        readonly: true,
        update: () => { },
    };

    setup() {
        this.fieldService = useService("field");
        this.loadFieldInfo = useLoadFieldInfo(this.fieldService);
        this.makeGetFieldDef = useMakeGetFieldDef(this.fieldService);

        this.tree = null;
        this.showArchivedCheckbox = false;
        this.includeArchived = false;
        this.showCompanyFilterCheckbox = false;
        this.includeCompany = false;

        onWillStart(() => this.onPropsUpdated(this.props));
        onWillUpdateProps((np) => this.onPropsUpdated(np));
    }

    async onPropsUpdated(p) {
        let domain;
        let isSupported = true;
        try {
            domain = new Domain(p.domain);
        } catch {
            isSupported = false;
        }
        if (!isSupported) {
            this.tree = null;
            this.showArchivedCheckbox = false;
            this.includeArchived = false;
            return;
        }

        const tree = treeFromDomain(domain);

        const getFieldDef = await this.makeGetFieldDef(p.resModel, tree, ["active"]);

        this.tree = treeFromDomain(domain, {
            getFieldDef,
            distributeNot: !p.isDebugMode,
        });

        this.showArchivedCheckbox = this.getShowArchivedCheckBox(Boolean(getFieldDef("active")), p);
        this.includeArchived = false;
        if (this.showArchivedCheckbox) {
            if (this.tree.value === "&") {
                this.tree.children = this.tree.children.filter((child) => {
                    if (deepEqual(child, ARCHIVED_CONDITION)) {
                        this.includeArchived = true;
                        return false;
                    }
                    return true;
                });
                if (this.tree.children.length === 1) {
                    this.tree = this.tree.children[0];
                }
            } else if (deepEqual(this.tree, ARCHIVED_CONDITION)) {
                this.includeArchived = true;
                this.tree = treeFromDomain(`[]`);
            }
        }

        // Handle company filter checkbox
        this.showCompanyFilterCheckbox = true;
        this.includeCompany = false;

        if (this.tree) {
            if (this.tree.value === "&") {
                this.tree.children = this.tree.children.filter((child) => {
                    // Only remove the SPECIFIC company filter pattern used by toggle
                    // ['|', ('company_id', '=', False), ('company_id', 'in', [0])]
                    if (child.value === "|" && child.children && child.children.length === 2) {
                        const [first, second] = child.children;
                        if (deepEqual(first, COMPANY_CONDITION_FALSE) &&
                            deepEqual(second, COMPANY_CONDITION_IN)) {
                            this.includeCompany = true;
                            return false; // Remove this specific pattern
                        }
                    }
                    // Keep all other company_id conditions in the tree for manual editing
                    return true;
                });
                if (this.tree.children.length === 1) {
                    this.tree = this.tree.children[0];
                }
            } else if (this.tree.value === "|" && this.tree.children && this.tree.children.length === 2) {
                // Handle case where the entire tree is the company OR condition
                const [first, second] = this.tree.children;
                if (deepEqual(first, COMPANY_CONDITION_FALSE) &&
                    deepEqual(second, COMPANY_CONDITION_IN)) {
                    this.includeCompany = true;
                    this.tree = treeFromDomain(`[]`);
                }
            }
            // Don't remove other company_id conditions - let them show in the tree editor
        }
    }

    getShowArchivedCheckBox(hasActiveField, props) {
        return hasActiveField;
    }

    getDefaultCondition(fieldDefs) {
        return getDefaultCondition(fieldDefs);
    }

    getDefaultOperator(fieldDef) {
        return getDomainDisplayedOperators(fieldDef)[0];
    }

    getOperatorEditorInfo(fieldDef) {
        const operators = getDomainDisplayedOperators(fieldDef);
        return getOperatorEditorInfo(operators, fieldDef);
    }

    getPathEditorInfo(resModel, defaultCondition) {
        const { isDebugMode } = this.props;
        return {
            component: ModelFieldSelectorBits,
            extractProps: ({ update, value: path }) => {
                return {
                    path,
                    update,
                    resModel,
                    isDebugMode,
                    readonly: false,
                };
            },
            isSupported: (path) => [0, 1].includes(path) || typeof path === "string",
            defaultValue: () => defaultCondition.path,
            stringify: (path) => formatValue(path),
            message: _t("Invalid field chain"),
        };
    }

    toggleIncludeArchived() {
        this.includeArchived = !this.includeArchived;
        this.update(this.tree);
    }

    toggleApplyCompanyFilter() {
        this.includeCompany = !this.includeCompany;
        this.update(this.tree);
    }

    resetDomain() {
        this.props.update("[]");
    }

    onDomainInput(domain) {
        if (this.props.debugUpdate) {
            this.props.debugUpdate(domain);
        }
    }

    onDomainChange(domain) {
        this.props.update(domain, true);
    }

    update(tree) {
        const archiveDomain = this.includeArchived ? ARCHIVED_DOMAIN : `[]`;

        // Only add the toggle company domain if the checkbox is checked
        const companyDomain = this.includeCompany
            ? `["|", ("company_id", "=", False), ("company_id", "in", [0])]`
            : `[]`;

        const base = tree ? domainFromTree(tree) : `[]`;
        const finalDomain = Domain.and([base, archiveDomain, companyDomain]).toString();
        this.props.update(finalDomain);
    }
}

export class DomainSelectorBits2 extends Component {
    static template = "awdw.DomainSelectorBits";
    static components = { TreeEditorBits, CheckBox };
    static props = {
        domain: String,
        resModel: String,
        className: { type: String, optional: true },
        defaultConnector: { type: [{ value: "&" }, { value: "|" }], optional: true },
        isDebugMode: { type: Boolean, optional: true },
        readonly: { type: Boolean, optional: true },
        update: { type: Function, optional: true },
        debugUpdate: { type: Function, optional: true },
    };
    static defaultProps = {
        isDebugMode: false,
        readonly: true,
        update: () => { },
    };

    setup() {
        this.fieldService = useService("field");
        this.loadFieldInfo = useLoadFieldInfo(this.fieldService);
        this.makeGetFieldDef = useMakeGetFieldDef(this.fieldService);

        this.tree = null;
        this.showArchivedCheckbox = false;
        this.includeArchived = false;
        this.includeCompany = false;
        this.showCompanyFilterCheckbox = false;

        onWillStart(() => this.onPropsUpdated(this.props));
        onWillUpdateProps((np) => this.onPropsUpdated(np));
    }

    async onPropsUpdated(p) {
        let domain;
        let isSupported = true;
        try {
            domain = new Domain(p.domain);
        } catch {
            isSupported = false;
        }
        if (!isSupported) {
            this.tree = null;
            this.showArchivedCheckbox = false;
            this.includeArchived = false;
            return;
        }

        const tree = treeFromDomain(domain);

        const getFieldDef = await this.makeGetFieldDef(p.resModel, tree, ["active"]);

        this.tree = treeFromDomain(domain, {
            getFieldDef,
            distributeNot: !p.isDebugMode,
        });

        this.showArchivedCheckbox = this.getShowArchivedCheckBox(Boolean(getFieldDef("active")), p);
        this.includeArchived = false;
        if (this.showArchivedCheckbox) {
            if (this.tree.value === "&") {
                this.tree.children = this.tree.children.filter((child) => {
                    if (deepEqual(child, ARCHIVED_CONDITION)) {
                        this.includeArchived = true;
                        return false;
                    }
                    return true;
                });
                if (this.tree.children.length === 1) {
                    this.tree = this.tree.children[0];
                }
            } else if (deepEqual(this.tree, ARCHIVED_CONDITION)) {
                this.includeArchived = true;
                this.tree = treeFromDomain(`[]`);
            }
        }

        // Handle company filter - same logic as DomainSelectorBits
        this.showCompanyFilterCheckbox = true;
        this.includeCompany = false;

        const COMPANY_CONDITION_FALSE = condition("company_id", "=", false);
        const COMPANY_CONDITION_IN = condition("company_id", "in", [0]);

        if (this.tree) {
            if (this.tree.value === "&") {
                this.tree.children = this.tree.children.filter((child) => {
                    // Only remove the SPECIFIC company filter pattern used by toggle
                    if (child.value === "|" && child.children && child.children.length === 2) {
                        const [first, second] = child.children;
                        if (deepEqual(first, COMPANY_CONDITION_FALSE) &&
                            deepEqual(second, COMPANY_CONDITION_IN)) {
                            this.includeCompany = true;
                            return false;
                        }
                    }
                    // Keep all other company_id conditions in the tree for manual editing
                    return true;
                });
                if (this.tree.children.length === 1) {
                    this.tree = this.tree.children[0];
                }
            } else if (this.tree.value === "|" && this.tree.children && this.tree.children.length === 2) {
                const [first, second] = this.tree.children;
                if (deepEqual(first, COMPANY_CONDITION_FALSE) &&
                    deepEqual(second, COMPANY_CONDITION_IN)) {
                    this.includeCompany = true;
                    this.tree = treeFromDomain(`[]`);
                }
            }
        }
    }

    getShowArchivedCheckBox(hasActiveField, props) {
        return hasActiveField;
    }

    getDefaultCondition(fieldDefs) {
        return getDefaultCondition(fieldDefs);
    }

    getDefaultOperator(fieldDef) {
        return getDomainDisplayedOperators(fieldDef)[0];
    }

    getOperatorEditorInfo(fieldDef) {
        const operators = getDomainDisplayedOperators(fieldDef);
        return getOperatorEditorInfo(operators, fieldDef);
    }

    getPathEditorInfo(resModel, defaultCondition) {
        const { isDebugMode } = this.props;
        return {
            component: ModelFieldSelectorBits,
            extractProps: ({ update, value: path }) => {
                return {
                    path,
                    update,
                    resModel,
                    isDebugMode,
                    readonly: false,
                };
            },
            isSupported: (path) => [0, 1].includes(path) || typeof path === "string",
            defaultValue: () => defaultCondition.path,
            stringify: (path) => formatValue(path),
            message: _t("Invalid field chain"),
        };
    }

    toggleIncludeArchived() {
        this.includeArchived = !this.includeArchived;
        this.update(this.tree);
    }

    toggleApplyCompanyFilter() {
        this.includeCompany = !this.includeCompany;
        this.update(this.tree);
    }

    resetDomain() {
        this.props.update("[]");
    }

    onDomainInput(domain) {
        if (this.props.debugUpdate) {
            this.props.debugUpdate(domain);
        }
    }

    onDomainChange(domain) {
        this.props.update(domain, true);
    }

    update(tree) {
        const archiveDomain = this.includeArchived ? ARCHIVED_DOMAIN : `[]`;
        const companyDomain = this.includeCompany
            ? `["|", ("company_id", "=", False), ("company_id", "in", [0])]`
            : `[]`;
        const base = tree ? domainFromTree(tree) : `[]`;
        const finalDomain = Domain.and([base, archiveDomain, companyDomain]).toString();
        this.props.update(finalDomain);
    }
}
