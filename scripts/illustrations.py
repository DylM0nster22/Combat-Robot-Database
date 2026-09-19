"""Original schematic illustrations for the website.

These are drawn here rather than sourced from the web so the site ships with
imagery it actually owns. They are deliberately diagrammatic: a photo of a
vertical spinner tells you what one looks like, but a diagram with the
rotation direction, the bite point and the ground line tells you how it works.

Every shape uses a CSS class instead of a hard-coded colour, so the drawings
follow the page between light and dark themes. The SVGs get inlined into the
HTML for that reason — an <img> tag would not inherit the page's variables.
"""

VIEWBOX = "0 0 260 150"
GROUND_Y = 122


def _svg(title, desc, body):
    return (
        f'<svg viewBox="{VIEWBOX}" role="img" aria-labelledby="t d" class="bot-svg">'
        f'<title id="t">{title}</title><desc id="d">{desc}</desc>'
        f'<defs>'
        f'<marker id="ah" markerWidth="7" markerHeight="7" refX="5.5" refY="3" '
        f'orient="auto"><path d="M0,0 L6,3 L0,6 z" class="motion-fill"/></marker>'
        f'</defs>'
        f'{_ground()}{body}</svg>'
    )


def _ground():
    return (f'<line x1="8" y1="{GROUND_Y}" x2="252" y2="{GROUND_Y}" class="ground"/>'
            + "".join(f'<line x1="{x}" y1="{GROUND_Y}" x2="{x - 6}" y2="{GROUND_Y + 6}" '
                      f'class="ground hatch"/>' for x in range(16, 258, 12)))


def _wheel(cx, cy, r=13):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" class="wheel"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r * 0.35:.1f}" class="hub"/>')


def _chassis(x, y, w, h, rx=4):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="body"/>'


def _spin_arrow(cx, cy, r, clockwise=True):
    """A circular motion arrow around a spinning part."""
    sweep = 1 if clockwise else 0
    x1, y1 = cx, cy - r
    x2, y2 = (cx + r, cy) if clockwise else (cx - r, cy)
    return (f'<path d="M{x1},{y1} A{r},{r} 0 0,{sweep} {x2},{y2}" '
            f'class="motion" marker-end="url(#ah)" fill="none"/>')


def _label(x, y, text, anchor="middle"):
    return f'<text x="{x}" y="{y}" class="anno" text-anchor="{anchor}">{text}</text>'


def _impact(x, y):
    """A little impact star at the bite point."""
    spikes = []
    for dx, dy in ((0, -9), (6, -6), (9, 0), (6, 6), (0, 9), (-6, 6), (-9, 0), (-6, -6)):
        spikes.append(f'<line x1="{x}" y1="{y}" x2="{x + dx}" y2="{y + dy}" class="impact"/>')
    return "".join(spikes)


# --------------------------------------------------------------- archetypes

def vertical_spinner():
    body = (
        _chassis(74, 86, 104, 26)
        + _wheel(96, 112, 11) + _wheel(160, 112, 11)
        + f'<circle cx="52" cy="88" r="34" class="weapon"/>'
        + f'<circle cx="52" cy="88" r="7" class="hub"/>'
        + '<path d="M52,54 l9,5 l-9,5 z" class="weapon-tooth"/>'
        + '<path d="M22,96 l-4,-9 l10,1 z" class="weapon-tooth"/>'
        + '<path d="M78,100 l2,-10 l8,6 z" class="weapon-tooth"/>'
        + _spin_arrow(52, 88, 46, clockwise=True)
        + _impact(46, 54)
        + _label(130, 78, "chassis") + _label(52, 140, "disc climbs on contact")
    )
    return _svg("Vertical spinner",
                "Side view: a toothed disc spins on a horizontal axis at the front "
                "of the robot, throwing an opponent upward on impact.", body)


def vertical_bar_spinner():
    body = (
        _chassis(80, 86, 100, 26)
        + _wheel(100, 112, 11) + _wheel(162, 112, 11)
        + '<g transform="rotate(-24 56 84)">'
        + '<rect x="10" y="78" width="92" height="12" rx="3" class="weapon"/>'
        + '<path d="M10,78 l-8,6 l8,6 z" class="weapon-tooth"/>'
        + '<path d="M102,78 l8,6 l-8,6 z" class="weapon-tooth"/>'
        + '</g>'
        + f'<circle cx="56" cy="84" r="7" class="hub"/>'
        + _spin_arrow(56, 84, 50, clockwise=True)
        + _label(130, 78, "chassis") + _label(56, 140, "tip mass dominates the energy")
    )
    return _svg("Vertical bar spinner",
                "Side view: a long bar spins on a horizontal axis; nearly all of "
                "its stored energy sits in the two tips.", body)


def horizontal_bar_spinner():
    body = (
        '<ellipse cx="130" cy="76" rx="42" ry="30" class="body"/>'
        + '<rect x="18" y="69" width="224" height="14" rx="4" class="weapon"/>'
        + '<path d="M18,69 l-10,7 l10,7 z" class="weapon-tooth"/>'
        + '<path d="M242,69 l10,7 l-10,7 z" class="weapon-tooth"/>'
        + '<circle cx="130" cy="76" r="8" class="hub"/>'
        + _spin_arrow(130, 76, 54, clockwise=True)
        + _impact(18, 76)
        + _label(130, 126, "top view — sweeps a full circle", "middle")
    )
    return _svg("Horizontal bar spinner",
                "Top view: a bar spins on a vertical axis, sweeping a circle far "
                "wider than the robot itself.", body)


def undercutter():
    body = (
        _chassis(78, 74, 104, 30)
        + _wheel(100, 108, 11) + _wheel(160, 108, 11)
        + '<rect x="14" y="104" width="232" height="9" rx="3" class="weapon"/>'
        + '<path d="M14,104 l-8,4.5 l8,4.5 z" class="weapon-tooth"/>'
        + '<path d="M246,104 l8,4.5 l-8,4.5 z" class="weapon-tooth"/>'
        + '<circle cx="130" cy="108" r="6" class="hub"/>'
        + _label(130, 62, "bar rides just above the floor")
        + _label(130, 140, "attacks wheels and ground clearance")
    )
    return _svg("Undercutter",
                "Side view: a horizontal bar sweeps very low, striking wheels and "
                "anything below an opponent's armour line.", body)


def drum_spinner():
    body = (
        _chassis(92, 84, 96, 28)
        + _wheel(112, 112, 11) + _wheel(170, 112, 11)
        + '<circle cx="60" cy="96" r="28" class="weapon"/>'
        + '<circle cx="60" cy="96" r="6" class="hub"/>'
        + '<path d="M60,68 l8,4 l-8,5 z" class="weapon-tooth"/>'
        + '<path d="M32,96 l4,-8 l5,8 z" class="weapon-tooth"/>'
        + '<path d="M60,124 l-8,-4 l8,-5 z" class="weapon-tooth"/>'
        + '<path d="M88,96 l-4,8 l-5,-8 z" class="weapon-tooth"/>'
        + _spin_arrow(60, 96, 38, clockwise=True)
        + _impact(38, 116)
        + _label(60, 142, "low, wide, excellent bite")
    )
    return _svg("Drum spinner",
                "Side view: a wide toothed cylinder spins on a horizontal axis low "
                "to the floor, biting under an opponent's edge.", body)


def beater_bar():
    body = (
        _chassis(92, 84, 96, 28)
        + _wheel(112, 112, 11) + _wheel(170, 112, 11)
        + '<g transform="rotate(30 60 98)">'
        + '<rect x="30" y="92" width="60" height="12" rx="3" class="weapon"/>'
        + '</g>'
        + '<circle cx="60" cy="98" r="6" class="hub"/>'
        + _spin_arrow(60, 98, 36, clockwise=True)
        + _label(60, 142, "a drum's cheap cousin")
    )
    return _svg("Beater bar",
                "Side view: a simple bar spinning on a horizontal axis — a drum's "
                "geometry without the drum's fabrication cost.", body)


def eggbeater():
    body = (
        _chassis(96, 84, 92, 28)
        + _wheel(116, 112, 11) + _wheel(172, 112, 11)
        + '<ellipse cx="58" cy="96" rx="30" ry="26" class="weapon" fill="none"/>'
        + '<ellipse cx="58" cy="96" rx="14" ry="26" class="weapon" fill="none"/>'
        + '<line x1="28" y1="96" x2="88" y2="96" class="weapon-line"/>'
        + '<circle cx="58" cy="96" r="6" class="hub"/>'
        + _spin_arrow(58, 96, 36, clockwise=True)
        + _label(58, 142, "open cage, self-rights well")
    )
    return _svg("Eggbeater",
                "Side view: an open cage weapon spinning on a horizontal axis, "
                "light for its diameter and good at self-righting.", body)


def shell_spinner():
    body = (
        '<circle cx="130" cy="72" r="56" class="weapon" fill="none"/>'
        + '<circle cx="130" cy="72" r="48" class="weapon-inner" fill="none"/>'
        + '<path d="M74,72 l-12,-7 l0,14 z" class="weapon-tooth"/>'
        + '<path d="M186,72 l12,7 l0,-14 z" class="weapon-tooth"/>'
        + '<circle cx="130" cy="72" r="26" class="body"/>'
        + '<circle cx="130" cy="72" r="7" class="hub"/>'
        + _spin_arrow(130, 72, 64, clockwise=False)
        + _label(130, 143, "top view — the whole shell is the weapon")
    )
    return _svg("Full-body shell spinner",
                "Top view: the robot's entire outer shell rotates, so every angle "
                "of approach meets the weapon.", body)


def melty_brain():
    body = (
        '<circle cx="130" cy="72" r="46" class="body" fill="none"/>'
        + '<rect x="84" y="64" width="92" height="16" rx="4" class="weapon"/>'
        + '<circle cx="130" cy="72" r="6" class="hub"/>'
        + _wheel(104, 72, 9) + _wheel(156, 72, 9)
        + _spin_arrow(130, 72, 56, clockwise=True)
        + '<line x1="130" y1="16" x2="130" y2="2" class="motion" marker-end="url(#ah)"/>'
        + _label(130, 143, "spins its whole body, then translates")
    )
    return _svg("Melty brain",
                "Top view: the entire robot spins continuously and steers by "
                "pulsing the drive in sync with its rotation.", body)


def wedge():
    body = (
        '<path d="M34,120 L150,120 L150,82 Z" class="body"/>'
        + '<path d="M34,120 L150,82" class="edge"/>'
        + _wheel(120, 110, 11) + _wheel(150, 106, 9)
        + '<line x1="60" y1="70" x2="40" y2="106" class="motion" marker-end="url(#ah)"/>'
        + _label(96, 58, "get under, stay under")
        + _label(150, 143, "wedge angle decides everything")
    )
    return _svg("Wedge",
                "Side view: a low inclined plane whose only job is to get beneath "
                "the opponent and take their traction away.", body)


def lifter():
    body = (
        _chassis(88, 88, 104, 26)
        + _wheel(110, 114, 11) + _wheel(172, 114, 11)
        + '<path d="M88,96 L40,70" class="weapon-line thick"/>'
        + '<circle cx="88" cy="96" r="6" class="hub"/>'
        + '<path d="M56,92 A44,44 0 0,1 44,66" class="motion" marker-end="url(#ah)" fill="none"/>'
        + _label(140, 78, "chassis") + _label(60, 140, "arm lifts, driver pushes")
    )
    return _svg("Lifter",
                "Side view: a powered arm pivots upward to lift an opponent's "
                "front off the floor and remove its traction.", body)


def flipper():
    body = (
        _chassis(92, 92, 100, 22)
        + _wheel(114, 114, 11) + _wheel(174, 114, 11)
        + '<path d="M92,100 L44,84" class="weapon-line thick"/>'
        + '<circle cx="92" cy="100" r="6" class="hub"/>'
        + '<path d="M60,74 A56,56 0 0,1 74,34" class="motion" marker-end="url(#ah)" fill="none"/>'
        + '<circle cx="46" cy="40" r="11" class="body" opacity="0.5"/>'
        + _label(150, 82, "stored energy released at once")
        + _label(90, 143, "flipper — pneumatic or spring")
    )
    return _svg("Flipper",
                "Side view: an arm releases stored energy in a single stroke to "
                "throw an opponent into the air.", body)


def hammer():
    body = (
        _chassis(90, 92, 96, 22)
        + _wheel(112, 114, 11) + _wheel(166, 114, 11)
        + '<line x1="138" y1="92" x2="72" y2="46" class="weapon-line thick"/>'
        + '<circle cx="66" cy="42" r="11" class="weapon"/>'
        + '<circle cx="138" cy="92" r="6" class="hub"/>'
        + '<path d="M84,34 A70,70 0 0,1 56,86" class="motion" marker-end="url(#ah)" fill="none"/>'
        + _impact(50, 100)
        + _label(180, 74, "head mass x arc")
        + _label(110, 143, "hammer / axe")
    )
    return _svg("Hammer",
                "Side view: a weighted head swings through an arc, concentrating "
                "its energy into a single point of impact.", body)


def thwackbot():
    body = (
        '<circle cx="112" cy="76" r="26" class="body"/>'
        + _wheel(112, 52, 12) + _wheel(112, 100, 12)
        + '<rect x="136" y="71" width="100" height="10" rx="3" class="weapon"/>'
        + '<path d="M236,71 l10,5 l-10,5 z" class="weapon-tooth"/>'
        + '<path d="M96,44 A38,38 0 1,0 96,108" class="motion" marker-end="url(#ah)" fill="none"/>'
        + _label(130, 132, "top view — spins in place to swing the tail")
    )
    return _svg("Thwackbot",
                "Top view: the robot spins on its own axis so a rigid tail sweeps "
                "around and strikes — no weapon motor needed.", body)


def grabber():
    body = (
        _chassis(104, 88, 90, 26)
        + _wheel(124, 114, 11) + _wheel(178, 114, 11)
        + '<path d="M104,94 L52,74" class="weapon-line thick"/>'
        + '<path d="M104,104 L52,112" class="weapon-line thick"/>'
        + '<circle cx="104" cy="99" r="6" class="hub"/>'
        + '<path d="M58,64 L58,52" class="motion" marker-end="url(#ah)"/>'
        + '<path d="M58,122 L58,134" class="motion" marker-end="url(#ah)"/>'
        + _label(160, 78, "clamp, carry, control")
    )
    return _svg("Grabber / clamper",
                "Side view: two jaws close on an opponent so the driver can carry "
                "them to a wall or the pit.", body)


def crusher():
    body = (
        _chassis(100, 88, 96, 26)
        + _wheel(122, 114, 11) + _wheel(178, 114, 11)
        + '<path d="M100,92 L46,66 L54,80 L100,100 Z" class="weapon"/>'
        + '<circle cx="100" cy="96" r="6" class="hub"/>'
        + '<path d="M52,58 L58,74" class="motion" marker-end="url(#ah)"/>'
        + _impact(52, 86)
        + _label(160, 78, "slow, enormous force")
        + _label(90, 143, "crusher — pierces armour")
    )
    return _svg("Crusher",
                "Side view: a hardened beak driven by a high-force actuator "
                "punches through an opponent's armour.", body)


def rammer():
    body = (
        '<path d="M58,120 L172,120 L172,84 L58,96 Z" class="body"/>'
        + _wheel(140, 112, 11) + _wheel(168, 108, 9)
        + '<path d="M58,96 L26,104 L58,110 Z" class="weapon"/>'
        + '<line x1="196" y1="100" x2="216" y2="100" class="motion" marker-end="url(#ah)"/>'
        + _label(120, 66, "all drive, no weapon motor")
        + _label(120, 143, "rammer / spike")
    )
    return _svg("Rammer",
                "Side view: a reinforced nose and a powerful drivetrain — damage "
                "comes from the whole robot's momentum.", body)


def forkbot():
    body = (
        _chassis(96, 92, 96, 24)
        + _wheel(118, 114, 11) + _wheel(174, 114, 11)
        + '<path d="M96,110 L34,117 L96,117 Z" class="weapon"/>'
        + '<path d="M96,100 L40,112" class="weapon-line"/>'
        + _label(146, 80, "hinged forks skim the floor")
        + _label(110, 143, "control bot / forkbot")
    )
    return _svg("Forkbot",
                "Side view: thin hinged forks ride on the floor to slide under an "
                "opponent before they can get under you.", body)


def multibot():
    body = (
        '<rect x="44" y="58" width="60" height="44" rx="5" class="body"/>'
        + '<rect x="30" y="72" width="16" height="16" rx="2" class="weapon"/>'
        + '<rect x="150" y="58" width="60" height="44" rx="5" class="body"/>'
        + '<rect x="208" y="72" width="16" height="16" rx="2" class="weapon"/>'
        + _label(74, 118, "bot A") + _label(180, 118, "bot B")
        + _label(127, 40, "one weight limit, split two ways")
    )
    return _svg("Multibot",
                "Top view: the class weight limit is divided between two or more "
                "robots that fight as a team.", body)


def walker():
    body = (
        _chassis(84, 66, 96, 28)
        + '<path d="M96,94 L84,120" class="leg"/><path d="M118,94 L114,120" class="leg"/>'
        + '<path d="M148,94 L152,120" class="leg"/><path d="M170,94 L182,120" class="leg"/>'
        + '<rect x="40" y="70" width="46" height="12" rx="3" class="weapon"/>'
        + _label(132, 56, "legs earn a weight bonus")
        + _label(132, 143, "walker")
    )
    return _svg("Walker",
                "Side view: legged locomotion instead of wheels, which most "
                "rulesets reward with a substantial weight bonus.", body)


def brick():
    body = (
        _chassis(70, 82, 120, 32)
        + _wheel(94, 114, 12) + _wheel(166, 114, 12)
        + '<rect x="58" y="90" width="14" height="20" rx="2" class="weapon"/>'
        + _label(130, 70, "no weapon — armour and drive")
        + _label(130, 143, "invertible brick")
    )
    return _svg("Invertible brick",
                "Side view: a symmetric armoured box that drives the same either "
                "way up and wins on control and survivability.", body)


def overhead_saw():
    body = (
        _chassis(96, 92, 100, 22)
        + _wheel(118, 114, 11) + _wheel(176, 114, 11)
        + '<line x1="150" y1="92" x2="92" y2="58" class="weapon-line thick"/>'
        + '<circle cx="80" cy="52" r="24" class="weapon" fill="none"/>'
        + '<circle cx="80" cy="52" r="5" class="hub"/>'
        + "".join(f'<line x1="{80 + 24 * __import__("math").cos(a)}" '
                  f'y1="{52 + 24 * __import__("math").sin(a)}" '
                  f'x2="{80 + 29 * __import__("math").cos(a)}" '
                  f'y2="{52 + 29 * __import__("math").sin(a)}" class="weapon-line"/>'
                  for a in [i * 0.5236 for i in range(12)])
        + _spin_arrow(80, 52, 34, clockwise=True)
        + _label(160, 78, "cuts on the way down")
    )
    return _svg("Overhead saw",
                "Side view: a spinning blade on a pivoting arm that comes down "
                "onto the top of an opponent.", body)


ARCHETYPE_ART = {
    "vertical-spinner": vertical_spinner,
    "vertical-bar-spinner": vertical_bar_spinner,
    "horizontal-bar-spinner": horizontal_bar_spinner,
    "undercutter": undercutter,
    "drum-spinner": drum_spinner,
    "beater-bar": beater_bar,
    "eggbeater": eggbeater,
    "shell-spinner": shell_spinner,
    "melty-brain": melty_brain,
    "wedge": wedge,
    "lifter": lifter,
    "flipper": flipper,
    "hammer": hammer,
    "thwackbot": thwackbot,
    "grabber": grabber,
    "crusher": crusher,
    "rammer": rammer,
    "forkbot": forkbot,
    "multibot": multibot,
    "walker": walker,
    "brick": brick,
    "overhead-saw": overhead_saw,
}

# Which drawing to use for an archetype whose id we don't have art for.
# Matched as substrings against the entity id and name, longest first.
ALIAS_HINTS = [
    # Specific weapon forms first: a "drum spinner (undercutter)" is a drum
    # before it is an undercutter, and the drum drawing is the informative one.
    ("eggbeater", "eggbeater"),
    ("egg-beater", "eggbeater"),
    ("egg beater", "eggbeater"),
    ("drum", "drum-spinner"),
    ("beater", "beater-bar"),
    ("shell", "shell-spinner"),
    ("full-body", "shell-spinner"),
    ("full body", "shell-spinner"),
    ("ring", "shell-spinner"),
    ("melty", "melty-brain"),
    ("translational", "melty-brain"),
    ("overhead-saw", "overhead-saw"),
    ("overhead saw", "overhead-saw"),
    ("saw", "overhead-saw"),
    ("thwack", "thwackbot"),
    ("hammer", "hammer"),
    ("axe", "hammer"),
    ("flipper", "flipper"),
    ("flip", "flipper"),
    ("lifter", "lifter"),
    ("lift", "lifter"),
    ("grabber", "grabber"),
    ("clamp", "grabber"),
    ("grappl", "grabber"),
    ("crusher", "crusher"),
    ("crush", "crusher"),
    ("pierc", "crusher"),
    ("multibot", "multibot"),
    ("swarm", "multibot"),
    ("walker", "walker"),
    ("shuffler", "walker"),
    ("fork", "forkbot"),
    ("rammer", "rammer"),
    ("spike", "rammer"),
    ("invertible", "brick"),
    ("brick", "brick"),
    # Orientation modifiers next: only reached when no specific form matched.
    ("undercut", "undercutter"),
    ("vertical-bar", "vertical-bar-spinner"),
    ("vert-bar", "vertical-bar-spinner"),
    ("horizontal", "horizontal-bar-spinner"),
    ("vertical", "vertical-spinner"),
    ("disc", "vertical-spinner"),
    ("disk", "vertical-spinner"),
    ("flywheel", "vertical-spinner"),
    # Broadest fallbacks last.
    ("wedge", "wedge"),
    ("control", "forkbot"),
    ("armor", "brick"),
    ("armour", "brick"),
    ("passive", "brick"),
    ("ram", "rammer"),
    ("spinner", "vertical-spinner"),
]


def art_for(entity_id, name="", tags=()):
    """Pick the best-matching drawing for an archetype entity.

    Matching runs in two passes. The id and name are authoritative, so they are
    tried first; tags are noisy (an entity about a drum is often tagged
    "undercutter" too) and only consulted when the name says nothing useful.
    """
    if entity_id in ARCHETYPE_ART:
        return ARCHETYPE_ART[entity_id]()
    stripped = entity_id.replace("archetype-", "")
    if stripped in ARCHETYPE_ART:
        return ARCHETYPE_ART[stripped]()

    primary = f"{entity_id} {name}".lower()
    for needle, key in ALIAS_HINTS:
        if needle in primary:
            return ARCHETYPE_ART[key]()

    secondary = " ".join(tags).lower()
    for needle, key in ALIAS_HINTS:
        if needle in secondary:
            return ARCHETYPE_ART[key]()
    return None


def all_art():
    return {key: func() for key, func in ARCHETYPE_ART.items()}
