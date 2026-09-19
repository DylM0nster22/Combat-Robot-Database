"""Real combat-robot photo references used by the static site.

The old site used generated SVG schematics selected by fuzzy name/tag matching.
That caused made-up-looking art to appear on archetypes and even unrelated pages.
This module intentionally uses an explicit allow-list: only archetypes with a
known real-world example get a photo.

Most photos are hosted by the NHRL Wiki and are linked rather than copied into
this repository because individual upload licensing varies. Other examples use
the original Robot Combat Archive, Robot Combat Events, RobotSearch, Make:, or
AutomationDirect image hosts. Detail pages always link back to the source page.
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


# NHRL examples
LYNX = _nhrl("Lynx", "Lynx-removebg.png")
FLYCUT = _nhrl("Flycut", "Flycut-June24.png")
ERUPTION = _nhrl("Eruption", "Eruption-December-2024.png")
ACTUAL_SIZE = _nhrl("Actual Size", "Actualsize-April26.png")
EVENT_HORIZON = _nhrl("Event Horizon", "EH MK5 Photo.jpg")
SINGULARITY = _nhrl("Singularity", "Singularity-removebg.png")
CHONKI = _nhrl("Chonki", "Chonkiv-dec-2024.png")
YOSHIMI = _nhrl("Yoshimi", "Yoshimi - August 2023.png")
LIFTOFF = _nhrl("Project LiftOff", "May 2026 Liftoff.jpg")
SAWMURAI = _nhrl("SawMurai", "SawMurai July-2020.jpg")
COLE = _nhrl("Cole", "Cole.png")
BEATER_BOY = _nhrl("Beater Boy", "Beaterboy-removebg.png")
WUMBO = _nhrl("Wumbo", "Wumbo-removebg.png")
MA_VERT = _nhrl("MA Vert", "MA Vert.jpg")
PRAMHEDA = _nhrl("Pramheda", "Pramheda-removebg.png")
JOHN_UNDERCUTTER = _nhrl("John Undercutter", "Johnundercutter-March25.png")
FIRST_LAW = _nhrl("1st Law", "1st Law V1.0.jpg")
RAM_PLAN = _nhrl("RAM PLAN", "RAM PLAN no BG.png")
COUNT_FORKULA = _nhrl("Count Forkula", "Countforkula-removebg.png")
EMULSIFIER = _nhrl("Emulsifier", "Emulsifier 2025.png")
RATFISH = _nhrl("Ratfish", "Ratfish may 2023.jpg")
SUBTRACTION = _nhrl("Subtraction", "Subtraction Both Configs.jpg")
KELPIE = _nhrl("Kelpie", "Keplie Nov-2020.jpg")
LIGHTWAVE = _nhrl("Lightwave", "Lightwave-Sept24.png")
INSIDE_JOB = _nhrl("Inside Job", "Insidejob 3lb July22.png")
LOOPHOLE = _nhrl("Loophole", "Loophole-removebg.png")
GAME_ON = _nhrl("Game On", "Gameon-removebg.png")
SPICY_TOUCAN = _nhrl("Spicy Toucan", "Spicytoucan-removebg.png")

# Robot Combat Archive examples
STINGER = _external(
    "Stinger",
    "https://www.robotcombatarchive.com/media/robot_images/2022/415_Stinger.png",
    "https://www.robotcombatarchive.com/robot/stinger",
    "Robot Combat Archive",
)
OVERKILL = _external(
    "OverKill",
    "https://www.robotcombatarchive.com/media/robot_images/2022/617_OverKill.jpeg",
    "https://www.robotcombatarchive.com/robot/overkill",
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
ORIGINAL_SIN = _external(
    "Original Sin",
    "https://www.robotcombatarchive.com/media/robot_images/2024/627389840_a692143049_b1.jpg",
    "https://www.robotcombatarchive.com/robot/original-sin",
    "Robot Combat Archive",
)
WEDGE_OF_DOOM = _external(
    "Wedge of Doom",
    "https://www.robotcombatarchive.com/media/robot_images/2022/110_WedgeofDoom.jpeg",
    "https://www.robotcombatarchive.com/robot/wedge-of-doom",
    "Robot Combat Archive",
)
STORM_II = _external(
    "Storm II",
    "https://www.robotcombatarchive.com/media/robot_images/2023/Storm_II_S71.png",
    "https://www.robotcombatarchive.com/robot/storm-ii",
    "Robot Combat Archive",
)
BIOHAZARD = _external(
    "BioHazard",
    "https://www.robotcombatarchive.com/media/robot_images/2022/1863_Biohazard.jpeg",
    "https://www.robotcombatarchive.com/robot/biohazard",
    "Robot Combat Archive",
)

# Plastic-ant and mechanism-specific examples from their original hosts.
ICE_SHADOW = _external(
    "Ice Shadow",
    "https://robotcombatevents.s3.amazonaws.com/uploads/resource/photo/12359/Screenshot_2025-01-28_at_3.14.05_PM.png",
    "https://www.robotcombatevents.com/groups/3063/resources/12359",
    "Robot Combat Events",
)
PABLO_ESCOBOT = _external(
    "Pablo Escobot",
    "https://robotcombatevents.s3.amazonaws.com/uploads/resource/photo/13916/Pablo_Escobot_Small.jpg",
    "https://www.robotcombatevents.com/groups/4339/resources/13916",
    "Robot Combat Events",
)
BLUE_DREAM = _external(
    "Blue Dream",
    "https://robotsearch-images.us-ord-1.linodeobjects.com/fullsize/21650f83ccbe8ae6e379b43cec9c0c0f.jpg",
    "https://robots.greenrobot.com/design/3795",
    "RobotSearch",
)
KERFUFFLE = _external(
    "Kerfuffle",
    "https://makezine.com/wp-content/uploads/2023/06/Figure-13.-Top-View-of-machine-1024x714.jpg",
    "https://makezine.com/projects/build-your-first-combat-bot/",
    "Make:",
)
LOCKJAW2 = _external(
    "Lock-Jaw2",
    "https://library.automationdirect.com/eemsushe/2016/09/Lockjaw-2.0-3-600x383.jpg",
    "https://library.automationdirect.com/lock-jaw2-robot-competes-battlebots-tv-show-using-automationdirect-parts/",
    "AutomationDirect",
)


# Every archetype gets a distinct real robot/photo. The pictured robot is a
# representative example of the design family, not a claim that the archetype
# itself is a specific robot.
PHOTOS = {
    "archetype-beater-bar": LYNX,
    "archetype-drum-spinner": FLYCUT,
    "archetype-eggbeater": ERUPTION,
    "archetype-flywheel": ACTUAL_SIZE,
    "archetype-ring-spinner": EVENT_HORIZON,
    "archetype-shell-spinner": CHONKI,
    "archetype-horizontal-bar-spinner": YOSHIMI,
    "archetype-melty-brain": LIFTOFF,
    "archetype-overhead-saw": SAWMURAI,
    "archetype-plastic-ant-beater-bar": BEATER_BOY,
    "archetype-plastic-ant-drum-spinner": PABLO_ESCOBOT,
    "archetype-plastic-ant-horizontal-spinner": WUMBO,
    "archetype-plastic-ant-vertical-spinner": ICE_SHADOW,
    "archetype-undercutter": JOHN_UNDERCUTTER,
    "archetype-vertical-bar-spinner": MA_VERT,
    "archetype-vertical-disc-spinner": PRAMHEDA,
    "archetype-wedge-spinner-hybrid": FIRST_LAW,
    "archetype-control-bot": RAM_PLAN,
    "archetype-armor-bot": STORM_II,
    "archetype-forkbot": COUNT_FORKULA,
    "archetype-invertible-brick": ORIGINAL_SIN,
    "archetype-plastic-ant-wedge-control": BLUE_DREAM,
    "archetype-tracked-bot": EMULSIFIER,
    "archetype-wedge": WEDGE_OF_DOOM,
    "archetype-flipper-electric": RATFISH,
    "archetype-lifter": SUBTRACTION,
    "archetype-linear-lifter": BIOHAZARD,
    "archetype-plastic-ant-lifter": KERFUFFLE,
    "archetype-flipper-pneumatic": KELPIE,
    "archetype-flipper-spring": LOCKJAW2,
    "archetype-crusher": INSIDE_JOB,
    "archetype-grabber-clamper": LIGHTWAVE,
    "archetype-hammer": SPICY_TOUCAN,
    "archetype-hammer-saw": COLE,
    "archetype-overhead-thwack": OVERKILL,
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
