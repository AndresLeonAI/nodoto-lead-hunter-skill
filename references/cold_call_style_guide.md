# Guion de llamada en frío — cómo escribir `cold_call_hook` (v3.2)

> Añadido 2026-09-15 por directiva explícita del usuario: el objetivo de este
> campo es **maximizar la tasa de reuniones agendadas** cuando Mateo (o quien
> llame) usa el Excel como guion de apoyo en una llamada en frío. No es un
> resumen técnico para análisis interno — para eso ya existen `website_problem`
> y `website_evidence`, que se mantienen sin cambios (evidencia verificable,
> exigida por el gate de calidad). `cold_call_hook` es la traducción de esa
> misma evidencia a algo que se puede decir casi textual por teléfono.

## Regla no negociable: nunca inventar

`cold_call_hook` se construye ÚNICAMENTE a partir de `website_problem` y
`website_evidence` ya verificados para ese lead. Nunca agrega un dato nuevo
(una cifra, un nombre, una fecha, una promesa de resultado) que no esté ya
respaldado por esa evidencia. Es un cambio de **voz y formato**, no de
contenido: de una nota técnica en tercera persona para un analista, a una
frase hablada en segunda persona dirigida al dueño del negocio.

## Estructura de 3 partes (2-3 frases, nunca un párrafo largo)

1. **Apertura de curiosidad, nunca acusatoria** — "Entré a su sitio buscando
   [algo natural: información suya, cómo agendar, conocer su equipo]..." o
   "Noté que cuando..." El tono es el de alguien que genuinamente investigó
   el negocio antes de llamar, no un auditor señalando un error.
2. **El hallazgo, en lenguaje de impacto de negocio, no jerga técnica** —
   traduce el hallazgo técnico a lo que el dueño realmente le importa: un
   cliente que se pierde, una cita que no se agenda, una llamada que no
   entra, confianza que se pierde. Nunca repitas la jerga tal cual ("error
   404", "sin certificado SSL", "widget embebido") sin traducirla a qué
   significa para un cliente real intentando contactarlo.
3. **Puente suave hacia la reunión** — una pregunta corta, de bajo
   compromiso, nunca un cierre agresivo de venta: "¿Tiene 15 minutos esta
   semana para que le muestre exactamente qué está pasando?" o "¿Le sirve que
   se lo muestre en una llamada corta?". Nunca prometas un resultado
   específico ("le puedo triplicar sus citas") — eso sería inventar, no está
   en la evidencia.

## Tono

- Español neutro/colombiano, formal-cercano ("usted", no "tú"; salvo que el
  decisor sea claramente un profesional joven/digital y el negocio use un
  tono informal en sus propias redes — en ese caso "tú" es aceptable).
- Corto: 2-3 frases. Un guion de llamada que no se pueda decir de un
  respiro suena a lectura, no a conversación.
- Concreto y específico al negocio (usa el nombre del problema real, nunca
  una plantilla genérica que podría aplicar a cualquier sitio).
- Nunca condescendiente ni alarmista. El objetivo es que el dueño sienta que
  alguien se tomó el tiempo de mirar su negocio de verdad, no que lo están
  presionando.

## Tabla de traducción: hallazgo técnico → lenguaje de impacto

Estos son patrones recurrentes encontrados en corridas anteriores (ver
`docs/run_log.md` del repo de memoria) — úsalos como referencia de tono, pero
la frase final siempre debe basarse en la evidencia específica de ESE lead,
nunca copiada literal de aquí.

| Hallazgo técnico (website_problem/evidence) | Traducción de impacto | Ejemplo de gancho |
|---|---|---|
| Sitio en HTTP plano, sin SSL | El navegador le muestra "no seguro" al visitante, justo antes de agendar | "Cuando entré a su sitio para agendar por el Calendly que tienen, el navegador me mostró la advertencia de 'sitio no seguro' — eso puede estar espantando a más de un cliente potencial antes de que llegue a la cita." |
| Página de equipo/nosotros rota (404) o solo en otro idioma | El paciente/cliente no puede confirmar quién lo va a atender | "Busqué quién lo iba a atender a mí como paciente y el enlace a 'Nuestro Equipo' me dio error — la única página donde sí aparece usted como director está en inglés, no en español." |
| Solo WhatsApp/widget de agendamiento, sin teléfono visible | Se pierde al cliente que prefiere llamar directo | "No encontré ningún número visible para simplemente llamar — todo pasa por un widget o WhatsApp. Con la visibilidad que ya tiene en prensa, eso puede estar dejando ir prospectos que prefieren hablar directo con usted." |
| Formulario de contacto no envía confirmación / falla silenciosamente | El cliente cree que escribió y usted nunca se entera | "Probé su formulario de agendamiento como si fuera un paciente nuevo y no me llegó ninguna confirmación — quiere decir que puede estar perdiendo citas sin saberlo." |
| Sitio comprometido con spam/hackeo (casinos, apuestas) | Riesgo de credibilidad y seguridad, urgente | "Entré a su sitio y encontré contenido de casinos en línea mezclado con su página real — eso no solo se ve mal, puede estar dañando cómo lo encuentra Google." |
| Solo PBX/conmutador general, sin decisor identificable como línea propia | No hay manera de saber si se está hablando con quien decide | (Estos leads normalmente NO califican — no se genera `cold_call_hook` de venta para un negocio sin decisor identificado; ver más abajo). |
| Menú/bloques duplicados, contenido roto/placeholder visible | Se ve descuidado justo cuando se compite por confianza en un servicio de alto ticket | "Al entrar a su sitio el menú aparece repetido dos veces y hay una sección que dice 'imagen pendiente' — para un negocio de su nivel, eso puede estar restándole la confianza que sus pacientes/clientes esperan." |

## Cuándo NO generar un gancho de venta

Si el lead no califica (`Owner Phone Confidence` no es `DIRECT` ni
`NAMED_ATTRIBUTION`, o no hay decisor identificado), `cold_call_hook` se deja
como `NOT_VERIFIED` — no tiene sentido escribir un guion de llamada para un
negocio al que todavía no se le puede llamar al decisor correcto. El
`Qué decirle en la llamada` del clean export para esos casos debe indicar
claramente que no hay teléfono de decisor verificado, nunca inventar un
gancho como si calificara.

## Quién lo escribe

El sub-agente que investiga cada lead escribe `cold_call_hook` como parte del
mismo paso de auditoría del sitio web (paso 5 del pipeline) — tiene el
contexto completo del negocio, el decisor y la evidencia fresca en memoria,
así que puede escribir algo específico y natural. `report.py` incluye un
`_fallback_cold_call_hook()` puramente mecánico (traduce la tercera persona a
segunda persona sin reescribir el contenido) para leads investigados antes de
que este campo existiera — es una red de seguridad, nunca el camino
principal: produce frases correctas pero mecánicas, no el gancho natural que
un buen sub-agente puede escribir a mano. Nunca depender de él a propósito.
