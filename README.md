# Efemérides UNAL

Repositorio histórico y calendario navegable de fechas de creación, celebración y otros hitos institucionales de sedes, facultades, institutos y programas de la Universidad Nacional de Colombia.

El proyecto usa una estructura normalizada: una entidad puede tener uno, dos, tres o más hitos. Cada hito puede asociarse a un acto administrativo y a uno o varios documentos. Esto evita escoger artificialmente una sola fecha cuando la historia institucional conserva varias fechas jurídicamente o ceremonialmente relevantes.

## Publicación

El sitio es estático y está preparado para GitHub Pages. Active GitHub Pages desde Settings > Pages y seleccione la rama `main` y la carpeta raíz.

## Datos

`data/efemerides.json` contiene las entidades y los hitos derivados del archivo Excel original.

`data/validation_issues.json` registra inconsistencias detectadas entre las fechas y las columnas auxiliares Año/Mes para revisión humana.

## Documentos

Los PDF pueden guardarse dentro de `docs/actos/`. Cada documento puede enlazarse desde los datos mediante `pdf_url`. Si todavía no existe PDF, se conserva la fuente localizada y el estado se muestra como pendiente.

## Principio de trazabilidad

El sitio no borra fechas alternativas. Las presenta como hitos distintos y conserva el acto administrativo, la autoridad emisora y la fuente documental. Los datos pendientes permanecen visibles como pendientes hasta su verificación.
