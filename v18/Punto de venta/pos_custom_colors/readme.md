# POS Colores y Logos Personalizados (Odoo 18)

**Módulo:** `pos_custom_colors`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Sales / Point of Sale  
**Dependencias:** `point_of_sale`  
**Autor:** Abel Alejandro Acuña

Personaliza la **apariencia del Punto de Venta** por cada **configuración de POS** (`pos.config`): colores (primario/secundario/acento), **logo en el navbar** y **imagen de fondo**.

---

## ✅ Funcionalidades

### 1) Colores del POS (por cada POS)

Permite definir:

- **Color primario** (`primary_color`) – navbar, botones y elementos principales
- **Color secundario** (`secondary_color`) – hover, bordes y variaciones
- **Color de acento** (`accent_color`) – estados activos/destacados

Los colores se aplican mediante **variables CSS**:

- `--pos-primary-color`
- `--pos-secondary-color`
- `--pos-accent-color`

---

### 2) Logo en el navbar (centrado)

- Si se carga un **Logo personalizado** (`custom_logo`), se muestra en el **centro** del navbar del POS.
- Si **no hay logo** y se definió **Texto del Navbar** (`branding_text`), se muestra el texto (útil para “Sucursal Centro”, etc.).

El logo se sirve desde una ruta dinámica:

- `/pos/branding/logo/<config_id>`

---

### 3) Imagen de fondo

Permite cargar una **imagen de fondo** (`custom_background`) que se aplica al layout general del POS y la pantalla de productos.

Se sirve desde:

- `/pos/branding/background/<config_id>`

---

### 4) Estilos UI incluidos (CSS)

El módulo agrega estilos visuales (además de colores):

- fondo general y product screen con imagen opcional
- tarjetas de producto con degradado y hover con acento
- botones y teclado numérico (numpad) con estilos modernos
- carrito/líneas de pedido con resaltados
- botón de pago/validación con efectos
- estilos para elementos de “descuento/recargo” (`.payment-adjustment-indicator`) si existen en tu POS

---

## ⚙️ Configuración

1. Ir a **Punto de Venta → Configuración → Punto de Venta**
2. Abrir el POS deseado
3. En la sección **“PERSONALIZACIÓN DEL POS”**:
   - Activar **Usar Personalización** (`use_custom_branding`)
   - Elegir colores (widgets tipo color)
   - Cargar **Logo Personalizado** (opcional)
   - Definir **Texto del Navbar** (opcional, se usa si no hay logo)
   - Cargar **Imagen de Fondo** (opcional)

> Cada POS puede tener su branding propio (multi-sucursal / multi-terminal).

---

## 🧠 Cómo funciona (técnico)

### Carga dinámica del branding

El POS (frontend) aplica un patch a `Chrome` (POS App) para:

- detectar si `pos.config.use_custom_branding` está activado
- inyectar un `<link rel="stylesheet">` a una URL dinámica por configuración:
  - `/pos/branding/css/<config_id>`

Esa ruta genera solo las **variables CSS** (colores + URLs de logo y fondo):

- `--pos-logo-url`
- `--pos-background-image`

### Plantilla OWL

Extiende la plantilla del navbar `point_of_sale.Navbar` para:

- reemplazar el centro del header por el logo/branding

---

## 🔒 Seguridad / Acceso

Las rutas de logo/fondo/css usan `auth='user'`.  
El usuario debe estar autenticado y con permisos estándar para operar POS.

Además, se fuerza **no-cache** (headers `Cache-Control: no-store...`) para que los cambios se reflejen al abrir una nueva sesión del POS.

---

## ⚠️ Notas y consideraciones

- Algunas reglas CSS usan `color-mix(...)`, que requiere navegadores modernos.
- `background-attachment: fixed` puede comportarse distinto en tablets/móviles según el browser.
- El texto de branding se inyecta en CSS (si no hay logo). Si tu texto contiene comillas, conviene evitarlas.

---

## 📦 Assets incluidos

Se cargan en:

- `point_of_sale.assets`
- `point_of_sale._assets_pos`

Archivos:

- `static/src/xml/pos_custom_templates.xml`
- `static/src/js/pos_branding_loader.js`
- `static/src/css/pos_custom_styles.css`

---

## 🧩 Rutas HTTP (Controller)

- `/pos/branding/logo/<config_id>` → devuelve PNG del logo
- `/pos/branding/background/<config_id>` → devuelve JPEG de fondo
- `/pos/branding/css/<config_id>` → devuelve CSS con variables para esa config

---
