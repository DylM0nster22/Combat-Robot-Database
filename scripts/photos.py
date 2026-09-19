"""Real combat-robot photo references used by the static site.

The old site used generated SVG schematics selected by fuzzy name/tag matching.
That caused made-up-looking art to appear on archetypes and even unrelated pages.
This module intentionally uses an explicit allow-list: only archetypes with a
known real-world example get a photo.

Most photos are hosted by the NHRL Wiki and are linked rather than copied into
this repository because individual upload licensing varies. A few historical
archetypes use Robot Combat Archive images. Detail pages always link back to the
source page.
"""

from urllib.parse import quote


def _nhrl(robot, filename):
    encoded = quote(filename, safe="")
    return {
        "robot": robot,
        "image": "https://wiki.nhrl.io/wiki/index.php/Special:Redirect/file/" + encoded,
        "source": "https://wiki.nhrl.io/wiki/index.php?title=" + quote("File:" + filename, safe=""),
        "provider": "NHRL Wiki",
    }


def _external(robot, image, source, provider):
    return {"robot": robot, "image": image, "source": source, "provider": provider}


LYNX = _nhrl("Lynx", "Lynx-removebg.png")
FLYCUT = _nhrl("Flycut", "Flycut-June24.png")
ACTUAL_SIZE = _nhrl("Actual Size", "Actualsize-April26.png")
SINGULARITY = _nhrl("Singularity", "Singularity-removebg.png")
CHONKI = _nhrl("Chonki", "Chonkiv-dec-2024.png")
YOSHIMI = _nhrl("Yoshimi", "Yoshimi - August 2023.png")
LIFTOFF = _nhrl("Project LiftOff", "May 2026 Liftoff.jpg")
COLE = _nhrl("Cole", "Cole.png")
BEATER_BOY = _nhrl("Beater Boy", "Beaterboy-removebg.png")
WUMBO = _nhrl("Wumbo", "Wumbo-removebg.png")
MA_VERT = _nhrl("MA Vert", "MA Vert.jpg")
JOHN_UNDERCUTTER = _nhrl("John Undercutter", "Johnundercutter-March25.png")
FIRST_LAW = _nhrl("1st Law", "1st Law V1.0.jpg")
RAM_PLAN = _nhrl("RAM PLAN", "RAM PLAN no BG.png")
COUNT_FORKULA = _nhrl("Count Forkula", "Countforkula-removebg.png")
EMULSIFIER = _nhrl("Emulsifier", "Emulsifier 2025.png")
PRETTY_FLY = _nhrl("Pretty Fly", "Prettyfly-Oct24.jpg")
LIGHTWAVE = _nhrl("Lightwave", "Lightwave-Sept24.png")
INSIDE_JOB = _nhrl("Inside Job", "Insidejob 3lb July22.png")
LOOPHOLE = _nhrl("Loophole", "Loophole-removebg.png")
GAME_ON = _nhrl("Game On", "Gameon-removebg.png")
SPICY_TOUCAN = _nhrl("Spicy Toucan", "Spicytoucan-removebg.png")

STINGER = _external(
    "Stinger",
    "https://www.robotcombatarchive.com/media/robot_images/2022/415_Stinger.png",
    "https://www.robotcombatarchive.com/robot/stinger",
    "Robot Combat Archive",
)
RAMMING_SPEED = _external(
    "Ramming Speed",
    "https://www.robotcombatarchive.com/media/robot_images/2022/964_RammingSpeed.png",
    "https://www.robotcombatarchive.com/robot/ramming-speed",
    "Robot Combat Archive",
)
DRILL_TEAM = _external(
    "Drill Team",
    "https://www.robotcombatarchive.com/media/robot_images/2025/drill_team.jpg",
    "https://www.robotcombatarchive.com/robot/drill-team",
    "Robot Combat Archive",
)


# Explicit mappings only. Re-using a real robot for closely related variants is
# intentional; captions call it a representative example rather than claiming
# the pictured machine is the archetype itself.
PHOTOS = {
    "archetype-beater-bar": LYNX,
    "archetype-drum-spinner": FLYCUT,
    "archetype-eggbeater": LYNX,
    "archetype-flywheel": ACTUAL_SIZE,
    "archetype-ring-spinner": SINGULARITY,
    "archetype-shell-spinner": CHONKI,
    "archetype-horizontal-bar-spinner": YOSHIMI,
    "archetype-melty-brain": LIFTOFF,
    "archetype-overhead-saw": COLE,
    "archetype-plastic-ant-beater-bar": BEATER_BOY,
    "archetype-plastic-ant-drum-spinner": FLYCUT,
    "archetype-plastic-ant-horizontal-spinner": WUMBO,
    "archetype-plastic-ant-vertical-spinner": MA_VERT,
    "archetype-undercutter": JOHN_UNDERCUTTER,
    "archetype-vertical-bar-spinner": MA_VERT,
    "archetype-vertical-disc-spinner": ACTUAL_SIZE,
    "archetype-wedge-spinner-hybrid": FIRST_LAW,
    "archetype-control-bot": RAM_PLAN,
    "archetype-armor-bot": RAMMING_SPEED,
    "archetype-forkbot": COUNT_FORKULA,
    "archetype-invertible-brick": RAMMING_SPEED,
    "archetype-plastic-ant-wedge-control": RAM_PLAN,
    "archetype-tracked-bot": EMULSIFIER,
    "archetype-wedge": RAMMING_SPEED,
    "archetype-flipper-electric": PRETTY_FLY,
    "archetype-lifter": COUNT_FORKULA,
    "archetype-linear-lifter": COUNT_FORKULA,
    "archetype-plastic-ant-lifter": COUNT_FORKULA,
    "archetype-flipper-pneumatic": PRETTY_FLY,
    "archetype-flipper-spring": PRETTY_FLY,
    "archetype-crusher": INSIDE_JOB,
    "archetype-grabber-clamper": LIGHTWAVE,
    "archetype-hammer": SPICY_TOUCAN,
    "archetype-hammer-saw": COLE,
    "archetype-overhead-thwack": STINGER,
    "archetype-thwackbot": STINGER,
    "archetype-passive-spike": DRILL_TEAM,
    "archetype-rammer": RAMMING_SPEED,
    "archetype-multibot": LOOPHOLE,
    "archetype-shuffler": SINGULARITY,
    "archetype-walker": GAME_ON,
}


def photo_for(entity_id):
    """Return photo metadata for a known archetype, otherwise None."""
    return PHOTOS.get(entity_id)
