# Catálogo de referencias litúrgicas de Emaús

## Propósito

`ReferenciaLecturaLiturgica` guarda únicamente las citas bíblicas asignadas a una fecha. No almacena el texto de la Biblia. Los textos, cuando se disponga de una fuente y autorización adecuadas, continúan separados en `LecturaLiturgica`.

## Fuentes y confianza

1. **Arquidiócesis de Cuenca:** referencia local prioritaria. La muestra inicial procede de los PDF 507.pdf, 581.pdf y 633.pdf aportados para este proyecto.
2. **Misal.mx:** fuente complementaria en español. El importador captura las citas que puede reconocer en la página diaria. Los registros quedan con `validada=False` hasta contrastarlos.
3. **USCCB:** fuente de comparación para la estructura del Leccionario; su calendario es propio de Estados Unidos y no se debe aplicar automáticamente a Ecuador. Sus materiales también tienen restricciones de reproducción.

Un error HTTP 404 en Misal.mx se registra como página no publicada/no disponible; no significa que ese día carezca de lecturas.

## Primer conjunto de datos

`core/data/referencias_cuenca_muestra_2023_2025.csv` contiene 24 fechas tomadas de las tablas y celebraciones de los documentos:

- `507.pdf`: 11–18 de junio de 2023.
- `581.pdf`: 10–17 de noviembre de 2024.
- `633.pdf`: 9–16 de noviembre de 2025.

El comando `cargar_referencias_cuenca_muestra` carga estos registros como referencias validadas y deja constancia del PDF y la página de origen. Se conservan las citas tal como fueron transcritas; las abreviaturas pueden normalizarse en una fase posterior.

## Comandos

Después de actualizar el repositorio y revisar la migración:

```powershell
python manage.py migrate
python manage.py cargar_referencias_cuenca_muestra
```

Para consultar Misal.mx y guardar solo las citas de una fecha:

```powershell
python manage.py importar_referencias_liturgicas --desde 2026-11-13 --hasta 2026-11-13 --pausa 0
```

Para ampliar un intervalo histórico:

```powershell
python manage.py importar_referencias_liturgicas --desde 2026-01-01 --hasta 2026-11-13 --pausa 1
```

El importador no guarda textos bíblicos. Solo crea registros con primera lectura, salmo y Evangelio reconocidos; segunda lectura y aclamación pueden quedar vacías cuando no correspondan o no se detecten. Los registros automáticos quedan sin validar.

No se reemplazan registros validados salvo que se indiquen expresamente `--sobrescribir --forzar-validada`.

## Ciclos

- Domingo: A/B/C.
- Ferial del Tiempo Ordinario: I/II.
- Adviento, Navidad, Cuaresma y Pascua: secuencias propias; no se deben inferir solo por paridad.
- Las solemnidades y fiestas pueden reemplazar la lectura ferial y necesitan precedencia y calendario particular aprobados.

La fecha del primer domingo de Adviento determina el cambio de año litúrgico. El ciclo ferial I/II solo se asigna a los días feriales del Tiempo Ordinario; no se debe mostrar como ciclo activo en Adviento, Navidad, Cuaresma o Pascua.

## Estado y límites

Este catálogo es una base verificable y ampliable, no todavía un Leccionario completo de Ecuador. La muestra cubre 24 fechas. El importador Misal.mx aporta otras fechas según disponibilidad y calidad de extracción. Antes de usar las referencias para seleccionar textos en un servicio, se debe validar la precedencia de celebraciones y resolver cualquier diferencia entre Misal.mx y la Arquidiócesis de Cuenca.
