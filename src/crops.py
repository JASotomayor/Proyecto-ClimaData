from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CropSpecies:
    """Crop species shared by one or more agronomic scenarios."""

    key: str
    label: str
    description: str


@dataclass(frozen=True)
class CropStage:
    """Definition of a crop stage with an editable Kc profile."""

    key: str
    label: str
    start_day: int
    end_day: int
    kc_start: float
    kc_end: float
    critical: bool = False
    score_weight: float = 1.0
    notes: str = ""


@dataclass(frozen=True)
class CropScenario:
    """Agronomic scenario used by FAO and agroclimatic scoring.

    A scenario represents a production system within a species, for example
    maize early or maize late. This keeps the current app compatible while
    preparing the model for multiple extensive-crop systems.
    """

    key: str
    label: str
    species_key: str
    system_label: str
    description: str
    campaign_start_month: int
    campaign_start_day: int
    sowing_window_start_month: int
    sowing_window_start_day: int
    sowing_window_end_month: int
    sowing_window_end_day: int
    cycle_length_days: int
    reference_note: str
    methodology_notes: tuple[str, ...]
    assumptions: tuple[str, ...]
    score_notes: tuple[str, ...]
    stages: tuple[CropStage, ...]
    critical_stage_summary: str
    thermal_optimal_min_c: float
    thermal_optimal_max_c: float
    thermal_tolerant_min_c: float
    thermal_tolerant_max_c: float
    cold_penalty_threshold_c: float | None = None
    cold_penalty_cap_days: int = 4
    active: bool = True
    implemented: bool = True
    score_component_weights: dict[str, float] | None = None


# Backward-compatible alias used by the current app modules.
CropDefinition = CropScenario


MAIZE_SPECIES = CropSpecies(
    key="maize",
    label="Maiz",
    description="Especie base para escenarios de maiz temprano y maiz tardio.",
)
WHEAT_SPECIES = CropSpecies(
    key="wheat",
    label="Trigo",
    description="Especie base para escenarios trigueros de invierno.",
)
SOY_SPECIES = CropSpecies(
    key="soy",
    label="Soja",
    description="Especie base para soja de primera y soja de segunda.",
)

_SPECIES_REGISTRY = {
    MAIZE_SPECIES.key: MAIZE_SPECIES,
    WHEAT_SPECIES.key: WHEAT_SPECIES,
    SOY_SPECIES.key: SOY_SPECIES,
}


MAIZE_EARLY = CropScenario(
    key="maize_early",
    label="Maíz temprano",
    species_key=MAIZE_SPECIES.key,
    system_label="Maíz temprano",
    description=(
        "Maíz de siembra temprana (setiembre–octubre), ciclo 170 días. "
        "Floración estimada en enero; llenado en febrero–marzo. "
        "Ventana de siembra modelada con inicio fijo 1-oct para comparación histórica interanual."
    ),
    campaign_start_month=10,
    campaign_start_day=1,
    sowing_window_start_month=9,
    sowing_window_start_day=20,
    sowing_window_end_month=10,
    sowing_window_end_day=20,
    cycle_length_days=170,
    reference_note=(
        "Kc por etapa basados en FAO Paper 56 (Allen et al., 1998), tabla 12 para maíz. "
        "ETo: Hargreaves-Samani con factor regional 0.88 (INTA EEA Anguil). "
        "Calendario fenológico representativo para La Pampa central; ajustar por híbrido, "
        "fecha real de siembra y ambiente."
    ),
    methodology_notes=(
        "Inicio de campaña fijo (1-oct): permite comparación histórica sistemática, "
        "no representa la fecha de siembra real de cada año ni de cada lote.",
        "ETo: Hargreaves-Samani (FAO Paper 56) con Kc FAO tabla 12. ETc = ETo × Kc lineal entre inicio y fin de etapa.",
        "Balance hídrico = P bruta − ETc acumulada por etapa, sin almacenaje de suelo ni aporte de napa.",
        "Score = suma ponderada de componentes hídrico (ciclo + etapas críticas), térmico y completitud de datos.",
    ),
    assumptions=(
        "Siembra modelada el 1 de octubre con floración estimada ~día 56–95 del ciclo (R1).",
        "Sin riego ni aporte de napa en el balance.",
        "Precipitación como oferta bruta: no se modela escurrimiento, evaporación directa ni interceptación.",
        "Sin almacenaje de agua útil al inicio del ciclo: el balance arranca en cero cada campaña.",
    ),
    score_notes=(
        "Ponderación calibrada contra rendimientos MAGyP/SIIA, Dpto. Maracó (La Pampa), n=24 campañas (2001–2024).",
        "Calibración empírica: r(score_critical, rendimiento)=0.528 vs r(score_cycle, rendimiento)=0.262; el componente crítico "
        "discrimina mejor entre campañas buenas y malas. El componente térmico mostró r=−0.046 (sin aporte discriminante).",
        "Pesos ajustados: crítico 55 (↑ desde 42 del default), ciclo 20 (↓ desde 28), térmico 5 (↓ desde 10), confiabilidad 6. "
        "El score total máximo (87) se normaliza en la escala 0–100 por clip.",
        "Floración (R1) y llenado (R2–R6) tienen peso 1.5× y 1.4× respectivamente sobre el componente crítico.",
        "Penalizaciones no lineales por déficit crítico severo (P/ETc < 0.55) y por días fríos (Tmin < 5 °C).",
    ),
    score_component_weights={"cycle": 20.0, "critical": 55.0, "thermal": 5.0, "reliability": 6.0},
    stages=(
        CropStage(
            key="implantacion",
            label="Implantación",
            start_day=1,
            end_day=20,
            kc_start=0.35,
            kc_end=0.40,
            critical=False,
            score_weight=0.6,
            notes="Implantación y emergencia. Kc 0.35–0.40; demanda hídrica reducida.",
        ),
        CropStage(
            key="vegetativo",
            label="Crecimiento vegetativo",
            start_day=21,
            end_day=55,
            kc_start=0.45,
            kc_end=0.90,
            critical=False,
            score_weight=0.9,
            notes="Expansión foliar y crecimiento vegetativo rápido (V4–V12). Kc en ascenso hasta ~0.90.",
        ),
        CropStage(
            key="floracion",
            label="Floración y cuaje",
            start_day=56,
            end_day=95,
            kc_start=1.05,
            kc_end=1.20,
            critical=True,
            score_weight=1.5,
            notes="R1–R2: floración y cuaje. Déficit con Kc 1.05–1.20 compromete la sincronía espiga–estigma y el cuaje de granos. Etapa de mayor sensibilidad del cultivo.",
        ),
        CropStage(
            key="llenado",
            label="Llenado de grano",
            start_day=96,
            end_day=140,
            kc_start=1.20,
            kc_end=1.00,
            critical=True,
            score_weight=1.4,
            notes="R3–R6: llenado. Kc máximo (1.20). Déficit reduce el número y peso de granos por espiga.",
        ),
        CropStage(
            key="madurez",
            label="Madurez fisiológica",
            start_day=141,
            end_day=170,
            kc_start=0.85,
            kc_end=0.60,
            critical=False,
            score_weight=0.5,
            notes="Madurez fisiológica y secado. Kc en descenso; el déficit hídrico en este período tiene bajo impacto sobre rendimiento final.",
        ),
    ),
    critical_stage_summary="floración y llenado",
    thermal_optimal_min_c=21.0,
    thermal_optimal_max_c=26.5,
    thermal_tolerant_min_c=18.5,
    thermal_tolerant_max_c=29.0,
    cold_penalty_threshold_c=5.0,
    cold_penalty_cap_days=4,
    active=True,
    implemented=True,
)

MAIZE_LATE = CropScenario(
    key="maize_late",
    label="Maíz tardío",
    species_key=MAIZE_SPECIES.key,
    system_label="Maíz tardío",
    description=(
        "Maíz de siembra tardía (dic–ene), ciclo 160 días. Floración estimada en feb–mar; cosecha en may–jun. "
        "Ventana modelada con inicio fijo 15-dic para comparación histórica interanual."
    ),
    campaign_start_month=12,
    campaign_start_day=15,
    sowing_window_start_month=11,
    sowing_window_start_day=20,
    sowing_window_end_month=1,
    sowing_window_end_day=10,
    cycle_length_days=160,
    reference_note=(
        "Base inicial para maiz tardio inspirada en criterios FAO y en calendarios "
        "simplificados de siembra tardia. Debe ajustarse por fecha real, hibrido, "
        "ambiente y manejo."
    ),
    methodology_notes=(
        "La fecha de inicio usada para modelar campanas es fija y no representa siembras reales del lote.",
        "La evapotranspiracion de referencia usa Hargreaves-Samani como aproximacion por disponibilidad de datos.",
        "Los Kc por etapa son parametros base para comparacion relativa entre campanas tardias.",
        "El analisis expresa ajuste agroclimatico relativo y no predice rendimiento.",
    ),
    assumptions=(
        "Campana modelada con inicio fijo el 15 de diciembre.",
        "Sin riego explicitado en el balance.",
        "La precipitacion se toma como oferta bruta sin modelar infiltracion efectiva ni escurrimiento.",
        "No se considera almacenamiento de agua util del suelo ni aporte de napa.",
    ),
    score_notes=(
        "Ponderación transferida de la calibración empírica de maíz temprano (MAGyP/SIIA, Maracó, n=24 campañas).",
        "Se adoptaron los mismos pesos ajustados (crítico 55, ciclo 20, térmico 5, confiabilidad 6) porque MAGyP "
        "no desagrega rendimiento por fecha de siembra en Maracó. La transferencia es razonable dado que "
        "el patrón de sensibilidad al déficit en floración es similar entre fechas.",
        "El componente térmico tiene peso reducido (5 vs 10 del default): la validación empírica sobre maíz temprano "
        "mostró r=−0.046 entre componente térmico y rendimiento observado.",
        "Esta versión debe leerse como base comparativa; calibración directa de maíz tardío requiere desagregación de datos MAGyP.",
    ),
    score_component_weights={"cycle": 20.0, "critical": 55.0, "thermal": 5.0, "reliability": 6.0},
    stages=(
        CropStage(
            key="implantacion",
            label="Implantación",
            start_day=1,
            end_day=18,
            kc_start=0.35,
            kc_end=0.40,
            critical=False,
            score_weight=0.6,
            notes="Implantación y emergencia en siembra tardía. Kc 0.35–0.40.",
        ),
        CropStage(
            key="vegetativo",
            label="Crecimiento vegetativo",
            start_day=19,
            end_day=50,
            kc_start=0.45,
            kc_end=0.95,
            critical=False,
            score_weight=0.9,
            notes="Crecimiento vegetativo rápido bajo calendario tardío (dic–ene). Kc en ascenso hasta ~0.95.",
        ),
        CropStage(
            key="floracion",
            label="Floración y cuaje",
            start_day=51,
            end_day=85,
            kc_start=1.05,
            kc_end=1.20,
            critical=True,
            score_weight=1.5,
            notes="R1–R2 en maíz tardío (feb–mar): mayor riesgo de estrés térmico combinado (Tmax > 32 °C) que en siembra temprana. Alta sensibilidad al déficit.",
        ),
        CropStage(
            key="llenado",
            label="Llenado de grano",
            start_day=86,
            end_day=130,
            kc_start=1.20,
            kc_end=1.00,
            critical=True,
            score_weight=1.4,
            notes="R3–R6 en fechas tardías (mar–abr): Kc máximo (1.20). El enfriamiento otoñal puede acortar el período de llenado efectivo.",
        ),
        CropStage(
            key="madurez",
            label="Madurez fisiológica",
            start_day=131,
            end_day=160,
            kc_start=0.85,
            kc_end=0.60,
            critical=False,
            score_weight=0.5,
            notes="Madurez fisiológica y secado. Kc en descenso; el déficit hídrico en este período tiene bajo impacto sobre rendimiento final.",
        ),
    ),
    critical_stage_summary="floración y llenado",
    thermal_optimal_min_c=21.0,
    thermal_optimal_max_c=27.0,
    thermal_tolerant_min_c=18.0,
    thermal_tolerant_max_c=30.0,
    cold_penalty_threshold_c=5.0,
    cold_penalty_cap_days=4,
    active=True,
    implemented=True,
)

WHEAT = CropScenario(
    key="wheat",
    label="Trigo",
    species_key=WHEAT_SPECIES.key,
    system_label="Trigo",
    description=(
        "Trigo de invierno, ciclo ~190 días (jun–dic). Macollaje invernal, encañazón y espigazón en sep–oct, cosecha nov–dic. "
        "Ventana modelada con inicio fijo 15-jun para comparación histórica interanual."
    ),
    campaign_start_month=6,
    campaign_start_day=15,
    sowing_window_start_month=5,
    sowing_window_start_day=20,
    sowing_window_end_month=7,
    sowing_window_end_day=10,
    cycle_length_days=190,
    reference_note=(
        "Kc por etapa basados en FAO Paper 56 (Allen et al., 1998) para trigo de invierno. "
        "ETo: Hargreaves-Samani con factor regional 0.88 (INTA EEA Anguil). "
        "Calendario representativo para La Pampa central; ajustar por cultivar, grupo de calidad y fecha de siembra."
    ),
    methodology_notes=(
        "Inicio de campaña fijo (15-jun): comparación histórica sistemática, no representa la fecha real de siembra.",
        "ETo: Hargreaves-Samani (FAO Paper 56) con Kc FAO tabla 12 para trigo. ETc = ETo × Kc por etapa.",
        "Balance hídrico = P bruta − ETc acumulada por etapa, sin almacenaje de suelo ni aporte de napa.",
        "Score = suma ponderada: balance hídrico (ciclo + etapas críticas), temperatura media, días fríos y completitud.",
    ),
    assumptions=(
        "Siembra modelada el 15 de junio; encañazón estimada ~día 86 del ciclo (DC30–DC50).",
        "Sin riego ni aporte de napa en el balance.",
        "Precipitación como oferta bruta: sin almacenaje inicial, escurrimiento ni evaporación directa.",
        "Kc macollaje inicial ajustado a 0.45 para reflejar la demanda hídrica reducida en invierno pampeano.",
    ),
    score_notes=(
        "El score mantiene la misma estructura general para permitir comparación entre escenarios.",
        "Encañazón-espigazón y llenado reciben mayor peso por sensibilidad del trigo al estrés hídrico.",
        "El Kc del macollaje fue ajustado a 0.45 al inicio para reflejar la demanda reducida en invierno pampeano.",
        "Esta versión debe leerse como una base comparativa regional; debe ajustarse por cultivar y fecha real.",
    ),
    stages=(
        CropStage(
            key="implantacion",
            label="Implantación y macollaje",
            start_day=1,
            end_day=35,
            kc_start=0.35,
            kc_end=0.55,
            critical=False,
            score_weight=0.7,
            notes="Implantación, emergencia y arranque del macollaje. Kc 0.35–0.55; demanda invernal reducida.",
        ),
        CropStage(
            key="vegetativo",
            label="Macollaje y crecimiento",
            start_day=36,
            end_day=85,
            kc_start=0.45,
            kc_end=0.95,
            critical=False,
            score_weight=0.9,
            notes=(
                "Macollaje, encañe inicial y expansión del cultivo. "
                "Kc inicial ajustado a 0.45 para reflejar la demanda reducida "
                "durante el macollaje en condiciones invernales de la pampa "
                "(días cortos, temperaturas bajas, ETo limitada)."
            ),
        ),
        CropStage(
            key="floracion",
            label="Encañazón y espigazón",
            start_day=86,
            end_day=130,
            kc_start=1.00,
            kc_end=1.15,
            critical=True,
            score_weight=1.5,
            notes="DC30–DC65: encañazón, espigazón y antesis. Etapa crítica para número de granos. Heladas con Tmin ≤ −2 °C destruyen espiguillas. Kc 1.00–1.15.",
        ),
        CropStage(
            key="llenado",
            label="Llenado de grano",
            start_day=131,
            end_day=170,
            kc_start=1.10,
            kc_end=0.80,
            critical=True,
            score_weight=1.4,
            notes="Llenado de grano: define el peso final de los granos. Déficit hídrico reduce el PMG. Exceso de lluvia en este período compromete calidad panadera (calidad proteica, Hagberg).",
        ),
        CropStage(
            key="madurez",
            label="Madurez fisiológica",
            start_day=171,
            end_day=190,
            kc_start=0.70,
            kc_end=0.35,
            critical=False,
            score_weight=0.5,
            notes="Secado y madurez del cultivo.",
        ),
    ),
    critical_stage_summary="encañazón, espigazón y llenado",
    thermal_optimal_min_c=12.0,
    thermal_optimal_max_c=18.0,
    thermal_tolerant_min_c=9.0,
    thermal_tolerant_max_c=22.0,
    cold_penalty_threshold_c=-2.0,
    cold_penalty_cap_days=4,
    active=True,
    implemented=True,
)

SOY_FIRST = CropScenario(
    key="soy_first",
    label="Soja de primera",
    species_key=SOY_SPECIES.key,
    system_label="Soja de primera",
    description=(
        "Soja de primera, ciclo ~150 días (nov–abr). Vegetativo dic–ene, floración y cuaje feb–mar (R1–R3), llenado mar–abr (R5–R6). "
        "Ventana modelada con inicio fijo 1-nov para comparación histórica interanual."
    ),
    campaign_start_month=11,
    campaign_start_day=10,
    sowing_window_start_month=10,
    sowing_window_start_day=20,
    sowing_window_end_month=11,
    sowing_window_end_day=25,
    cycle_length_days=150,
    reference_note=(
        "Base inicial para soja de primera inspirada en criterios FAO y calendarios "
        "simplificados de soja temprana. Debe ajustarse por grupo, fecha real y ambiente."
    ),
    methodology_notes=(
        "La fecha de inicio usada para modelar campanas es fija y no representa fechas reales del lote.",
        "La evapotranspiracion de referencia usa Hargreaves-Samani como aproximacion por disponibilidad de datos.",
        "Los Kc por etapa son parametros base para comparacion relativa entre campanas sojeras.",
        "El analisis expresa ajuste agroclimatico relativo y no predice rendimiento.",
    ),
    assumptions=(
        "Campana modelada con inicio fijo el 10 de noviembre.",
        "Sin riego explicitado en el balance.",
        "La precipitacion se toma como oferta bruta sin modelar infiltracion efectiva ni escurrimiento.",
        "No se considera almacenamiento de agua util del suelo ni aporte de napa.",
    ),
    score_notes=(
        "Ponderación calibrada contra rendimientos MAGyP/SIIA, Dpto. Maracó (La Pampa), n=19 campañas (2001–2024).",
        "Calibración empírica: r(score_cycle, rendimiento)=0.540 > r(score_critical, rendimiento)=0.382. "
        "A diferencia del maíz, en soja el balance del ciclo completo es más discriminante que el de las etapas críticas aisladas.",
        "Pesos ajustados: ciclo 38 (↑ desde 28 del default), crítico 32 (↓ desde 42), térmico 5 (↓ desde 10), confiabilidad 6. "
        "Relación ciclo/crítico invertida respecto al maíz: la soja redistribuye mejor el déficit a lo largo del ciclo.",
        "Floración (R1–R3) y llenado de vainas (R4–R6) tienen peso 1.5× y 1.4× sobre el componente crítico.",
    ),
    score_component_weights={"cycle": 38.0, "critical": 32.0, "thermal": 5.0, "reliability": 6.0},
    stages=(
        CropStage(
            key="implantacion",
            label="Implantación",
            start_day=1,
            end_day=18,
            kc_start=0.40,
            kc_end=0.50,
            critical=False,
            score_weight=0.6,
            notes="Implantación y emergencia. Kc 0.35–0.40; demanda hídrica reducida.",
        ),
        CropStage(
            key="vegetativo",
            label="Crecimiento vegetativo",
            start_day=19,
            end_day=55,
            kc_start=0.55,
            kc_end=0.95,
            critical=False,
            score_weight=0.9,
            notes="V1–R0: desarrollo vegetativo y cierre del entresurco. Kc en ascenso hasta ~0.95.",
        ),
        CropStage(
            key="floracion",
            label="Floración y cuaje",
            start_day=56,
            end_day=95,
            kc_start=1.00,
            kc_end=1.15,
            critical=True,
            score_weight=1.5,
            notes="R1–R3: floración y fijación de vainas. Estrés hídrico o térmico (Tmax > 35 °C) provoca aborto de flores y caída de vainas. Etapa de mayor sensibilidad del cultivo.",
        ),
        CropStage(
            key="llenado",
            label="Formacion y llenado de vainas",
            start_day=96,
            end_day=125,
            kc_start=1.15,
            kc_end=0.95,
            critical=True,
            score_weight=1.4,
            notes="R4–R6: formación y llenado de granos. Kc máximo (1.10–1.15). Déficit reduce el número de semillas por vaina y el peso de 1000 granos.",
        ),
        CropStage(
            key="madurez",
            label="Madurez fisiológica",
            start_day=126,
            end_day=150,
            kc_start=0.85,
            kc_end=0.35,
            critical=False,
            score_weight=0.5,
            notes=(
                "Secado y madurez fisiológica. Kc final ajustado a 0.35 "
                "para reflejar la senescencia activa y reducción de cobertura "
                "foliar al final del ciclo (FAO-56 Kc_end soja ~0.30–0.40)."
            ),
        ),
    ),
    critical_stage_summary="floración y llenado",
    thermal_optimal_min_c=20.0,
    thermal_optimal_max_c=26.0,
    thermal_tolerant_min_c=17.0,
    thermal_tolerant_max_c=29.0,
    cold_penalty_threshold_c=5.0,
    cold_penalty_cap_days=4,
    active=True,
    implemented=True,
)

SOY_SECOND = CropScenario(
    key="soy_second",
    label="Soja de segunda",
    species_key=SOY_SPECIES.key,
    system_label="Soja de segunda",
    description=(
        "Soja de segunda tras trigo, ciclo ~130 días (dic–abr). Vegetativo comprimido, floración y cuaje feb–mar (R1–R3), llenado mar–abr (R5–R6). "
        "Mayor exposición a estrés térmico en R1 que la soja de primera. Ventana con inicio fijo 20-dic."
    ),
    campaign_start_month=12,
    campaign_start_day=15,
    sowing_window_start_month=12,
    sowing_window_start_day=1,
    sowing_window_end_month=1,
    sowing_window_end_day=15,
    cycle_length_days=130,
    reference_note=(
        "Base inicial para soja de segunda inspirada en criterios FAO y calendarios "
        "simplificados de siembra tardia. Debe ajustarse por fecha real, antecesor y ambiente."
    ),
    methodology_notes=(
        "La fecha de inicio usada para modelar campanas es fija y no representa fechas reales del lote.",
        "La evapotranspiracion de referencia usa Hargreaves-Samani como aproximacion por disponibilidad de datos.",
        "Los Kc por etapa son parametros base para comparacion relativa entre campanas tardias de soja.",
        "El analisis expresa ajuste agroclimatico relativo y no predice rendimiento.",
    ),
    assumptions=(
        "Campana modelada con inicio fijo el 15 de diciembre.",
        "Sin riego explicitado en el balance.",
        "La precipitacion se toma como oferta bruta sin modelar infiltracion efectiva ni escurrimiento.",
        "No se considera almacenamiento de agua util del suelo ni aporte de napa.",
    ),
    score_notes=(
        "Ponderación calibrada contra rendimientos MAGyP/SIIA, Dpto. Maracó (La Pampa), n=19 campañas (2001–2024).",
        "Calibración empírica: r(score_cycle, rendimiento)=0.512 > r(score_critical, rendimiento)=0.326. "
        "Patrón consistente con soja de primera: el balance del ciclo completo discrimina mejor entre campañas que el balance de etapas críticas aisladas.",
        "Pesos ajustados: ciclo 38 (↑ desde 28 del default), crítico 32 (↓ desde 42), térmico 5 (↓ desde 10), confiabilidad 6. "
        "Transferencia directa de la calibración de soja de primera (mismo comportamiento hídrico observado, misma serie MAGyP).",
        "Mayor exposición a estrés térmico en R1 que la soja de primera (floración cae en fechas más cálidas en soja tardía).",
    ),
    score_component_weights={"cycle": 38.0, "critical": 32.0, "thermal": 5.0, "reliability": 6.0},
    stages=(
        CropStage(
            key="implantacion",
            label="Implantación",
            start_day=1,
            end_day=15,
            kc_start=0.40,
            kc_end=0.50,
            critical=False,
            score_weight=0.6,
            notes="Implantación y emergencia en siembra tardía. Kc 0.35–0.40.",
        ),
        CropStage(
            key="vegetativo",
            label="Crecimiento vegetativo",
            start_day=16,
            end_day=45,
            kc_start=0.55,
            kc_end=0.95,
            critical=False,
            score_weight=0.9,
            notes="V1–R0: desarrollo vegetativo más comprimido en soja de segunda (15–20 días menos que primera). Cierre del entresurco más tardío.",
        ),
        CropStage(
            key="floracion",
            label="Floración y cuaje",
            start_day=46,
            end_day=80,
            kc_start=1.00,
            kc_end=1.15,
            critical=True,
            score_weight=1.5,
            notes="R1–R3: floración y fijación de vainas. Estrés hídrico o térmico (Tmax > 35 °C) provoca aborto de flores y caída de vainas. Etapa de mayor sensibilidad del cultivo.",
        ),
        CropStage(
            key="llenado",
            label="Formacion y llenado de vainas",
            start_day=81,
            end_day=108,
            kc_start=1.15,
            kc_end=0.95,
            critical=True,
            score_weight=1.4,
            notes="R4–R6 en soja de segunda: el período crítico cae en las mismas fechas que en soja de primera pero con mayor acumulación térmica previa. Evaluación clave del balance hídrico.",
        ),
        CropStage(
            key="madurez",
            label="Madurez fisiológica",
            start_day=109,
            end_day=130,
            kc_start=0.80,
            kc_end=0.35,
            critical=False,
            score_weight=0.5,
            notes=(
                "Secado y madurez fisiológica. Kc final ajustado a 0.35 "
                "para reflejar la senescencia y reducción de cobertura foliar "
                "al fin del ciclo de soja de segunda (FAO-56 Kc_end ~0.30–0.40)."
            ),
        ),
    ),
    critical_stage_summary="floración y llenado",
    thermal_optimal_min_c=20.0,
    thermal_optimal_max_c=27.0,
    thermal_tolerant_min_c=17.0,
    thermal_tolerant_max_c=30.0,
    cold_penalty_threshold_c=5.0,
    cold_penalty_cap_days=4,
    active=True,
    implemented=True,
)

# Backward-compatible alias for existing callers and historical naming.
MAIZE = MAIZE_EARLY

_CROP_SCENARIOS = {
    MAIZE_EARLY.key: MAIZE_EARLY,
    MAIZE_LATE.key: MAIZE_LATE,
    WHEAT.key: WHEAT,
    SOY_FIRST.key: SOY_FIRST,
    SOY_SECOND.key: SOY_SECOND,
}
_SCENARIO_ALIASES = {
    "maize": MAIZE_EARLY.key,
}


def _resolve_scenario_key(crop_key: str) -> str:
    """Resolve legacy keys and scenario aliases to a canonical scenario id."""
    return _SCENARIO_ALIASES.get(crop_key, crop_key)


def list_crop_species() -> list[CropSpecies]:
    """Return crop species in display order."""
    return list(_SPECIES_REGISTRY.values())


def get_crop_species(species_key: str) -> CropSpecies:
    """Return a crop species by key."""
    try:
        return _SPECIES_REGISTRY[species_key]
    except KeyError as exc:
        available = ", ".join(sorted(_SPECIES_REGISTRY))
        raise ValueError(
            f"Especie no soportada: {species_key}. Disponibles: {available}."
        ) from exc


def get_crop_scenario(crop_key: str) -> CropScenario:
    """Return any configured crop scenario, including future placeholders."""
    scenario_key = _resolve_scenario_key(crop_key)
    try:
        return _CROP_SCENARIOS[scenario_key]
    except KeyError as exc:
        available = ", ".join(sorted(_CROP_SCENARIOS))
        raise ValueError(
            f"Escenario no soportado: {crop_key}. Disponibles: {available}."
        ) from exc


def list_crop_scenarios(include_future: bool = False) -> list[CropScenario]:
    """Return scenarios available for the app, optionally including future placeholders."""
    scenarios = list(_CROP_SCENARIOS.values())
    if include_future:
        return scenarios
    return [scenario for scenario in scenarios if scenario.active and scenario.implemented]


def list_active_crop_scenarios() -> list[CropScenario]:
    """Return active, implemented scenarios shown in the current app."""
    return list_crop_scenarios(include_future=False)


def list_future_crop_scenarios() -> list[CropScenario]:
    """Return configured but not yet implemented scenarios."""
    return [
        scenario
        for scenario in _CROP_SCENARIOS.values()
        if not (scenario.active and scenario.implemented)
    ]


def get_crop_definition(crop_key: str) -> CropDefinition:
    """Backward-compatible accessor used by the current app modules.

    This only returns active, implemented scenarios to avoid routing the current
    FAO and scoring flow into placeholders that still lack agronomic detail.
    """
    scenario = get_crop_scenario(crop_key)
    if not (scenario.active and scenario.implemented):
        available = ", ".join(s.key for s in list_active_crop_scenarios())
        raise ValueError(
            f"Escenario no activo todavia: {crop_key}. Activos actuales: {available}."
        )
    return scenario


def list_crop_definitions() -> list[CropDefinition]:
    """Backward-compatible list of active crop definitions used by the current UI."""
    return list_active_crop_scenarios()
