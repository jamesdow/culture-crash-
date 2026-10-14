"""Far domains the latent dive is forced into.

Distance is enforced on purpose: each shortlisted space draws a few of these at
random, and the model has to find a real, structurally matching concept inside
each one. Add your own, the stranger and more specific the better.
"""

from __future__ import annotations

import random

FAR_DOMAINS: list[str] = [
    # life sciences
    "mycology and fungal networks", "lichenology", "bryology (mosses)", "forensic entomology",
    "parasitology", "symbiosis in deep-sea vent ecosystems", "coral reproduction",
    "bacterial quorum sensing", "plant grafting and rootstocks", "seed dormancy and seed banks",
    "hermit crab shell-vacancy chains", "corvid cognition", "bird migration and navigation",
    "ant colony foraging", "honeybee swarm decision-making", "slime mould behaviour",
    "tardigrade cryptobiosis", "salt marsh ecology", "invasive species management",
    "fermentation microbiology", "cheese affinage", "pollination ecology", "animal hibernation physiology",
    "wolf pack territorial behaviour", "cuckoo brood parasitism", "eel migration",
    # earth and sky
    "glaciology", "karst hydrology", "permafrost science", "volcanology", "plate tectonics",
    "tidal science", "sediment and delta formation", "dendrochronology (tree rings)",
    "orbital mechanics", "radio astronomy", "meteorite hunting", "weather folklore",
    "avalanche forecasting", "desert dune migration", "cave formation (speleogenesis)",
    # craft and making
    "dry-stone walling", "Japanese wood joinery", "bookbinding", "kiln firing and glazes",
    "bell founding and change ringing", "clockmaking escapements", "letterpress typography",
    "blacksmithing and annealing", "perfumery", "textile conservation", "bonsai",
    "hedge laying", "coppicing", "thatching", "violin making (luthiery)", "glassblowing",
    "sourdough culture maintenance", "natural dyeing", "paper marbling", "mosaic restoration",
    # law, institutions, systems
    "maritime salvage law", "medieval guild apprenticeship", "Roman property law",
    "insolvency and bankruptcy law", "wine appellation rules", "common land and grazing rights",
    "Victorian postal system", "railway signalling", "air traffic control phraseology",
    "harbour pilotage", "auction house practice", "archival appraisal", "museum deaccessioning",
    "patent law", "diplomatic protocol", "lighthouse keeping", "monastic rules and the horarium",
    "the Jubilee year and debt release", "lexicography and dictionary making", "heraldry",
    "court jester traditions", "stock exchange circuit breakers", "insurance underwriting history",
    # navigation, movement, endurance
    "Polynesian wayfinding", "high-altitude mountaineering physiology", "free diving",
    "ice road trucking", "submarine operations", "polar expedition logistics",
    "long-distance sailing watch systems", "cave diving", "pigeon racing", "falconry",
    "Sami reindeer herding", "transhumance and seasonal grazing", "caravanserai trade routes",
    # mind, ritual, performance
    "stage magic and misdirection", "orchestral conducting", "Byzantine liturgy",
    "Talmudic disputation", "Quaker meeting practice", "Victorian mourning customs",
    "Japanese tea ceremony etiquette", "sumo stable life", "improv theatre rules",
    "puppetry", "circus rigging", "carnival and festival inversion rituals",
    "oral epic poetry (formulaic composition)", "memory palaces", "monastic silence",
    # science and engineering
    "cryogenics", "metallurgy and work hardening", "acoustics of cathedrals",
    "materials fatigue", "bridge expansion joints", "control theory and feedback",
    "error-correcting codes", "cartographic projection", "game theory", "epidemiology",
    "pharmacology half-lives", "radioactive decay and carbon dating", "aviation black boxes",
    "swarm robotics", "quantum decoherence", "signal processing and noise",
    "museum conservation science", "forensic accounting", "typography and kerning",
    "urban drainage engineering", "power grid load balancing",
]


def draw(n: int, rng: random.Random, exclude: set[str] | None = None) -> list[str]:
    pool = [d for d in FAR_DOMAINS if not exclude or d not in exclude]
    return rng.sample(pool, min(n, len(pool)))
