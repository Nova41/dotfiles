"""
Provides a full-width tab bar with fixed-sized tabs to the left and a status bar to
the right. The layout is visualized as follows:

[LOGO][(TAB 1)(TAB 2) ...]                                    [BATTERY] [TIME] [DATE]

COMPATIBILITY

This plugin only supports MacOS.

OPTIONS

USE_REPAINT_TIMER   If enabled, the tab bar is force-repainted every second.
                    By default, the status bar only gets updated passively when kitty
                    repaints and can never exceed the configured `repaint_delay`
                    (default is 2s).
                    Note: Repaint will still subject to OS's repaint scheduling, i.e.
                    OS might suspend kitty's repainting when the app is running in
                    background or has no foreground activity.
"""


# pyright: reportMissingImports=false
from datetime import datetime
from subprocess import CalledProcessError, check_output
from time import time

from kitty.fast_data_types import add_timer, get_boss, get_options, remove_timer, Screen
from kitty.tab_bar import (
    DrawData,
    ExtraData,
    Formatter,
    TabBarData,
    as_rgb,
    draw_attributed_string,
    draw_title,
)
from kitty.utils import color_as_int


# ------------------ Config ------------------
USE_REPAINT_TIMER = False
USE_DEBUG_LOGGING = False
# ------------------ Config ------------------


opts = get_options()
ICON_FG = as_rgb(color_as_int(opts.color16))
ICON_BG = as_rgb(color_as_int(opts.color8))
BATTERY_TEXT_FG = as_rgb(color_as_int(opts.foreground))
DATE_FG = as_rgb(color_as_int(opts.color8))
TIME_FG = as_rgb(color_as_int(opts.foreground))
SEPARATOR_SYMBOL, SOFT_SEPARATOR_SYMBOL = ("", "")
RIGHT_MARGIN = 1
REFRESH_TIME = 1
BRAND_ICON = " 󰸏  "
UNPLUGGED_ICONS = {
    10: "󰁺",
    20: "󰁻",
    30: "󰁼",
    40: "󰁽",
    50: "󰁾",
    60: "󰁿",
    70: "󰂀",
    80: "󰂁",
    90: "󰂂",
    100: "󰁹",
}
PLUGGED_ICONS = {
    10: "󰢜",
    20: "󰂆",
    30: "󰂇",
    40: "󰂈",
    50: "󰢝",
    60: "󰂉",
    70: "󰢞",
    80: "󰂊",
    90: "󰂋",
    99: "󰂅",
    100: "󰂄",
}
UNKNOWN_ICON = "󰂑"
UNPLUGGED_COLORS = {
    15: as_rgb(color_as_int(opts.color1)),
    16: as_rgb(color_as_int(opts.color11)),
    30: as_rgb(color_as_int(opts.color15)),
}
PLUGGED_COLORS = {
    15: as_rgb(color_as_int(opts.color1)),
    16: as_rgb(color_as_int(opts.color11)),
    30: as_rgb(color_as_int(opts.color6)),
    99: as_rgb(color_as_int(opts.color6)),
    100: as_rgb(color_as_int(opts.color2)),
}

timer_id = None
len_info_cells = -1
cached_battery_cells = {}
cached_battery_cells_updated_at = 0


def _log(message, *args):
    if USE_DEBUG_LOGGING == False:
        return
    print(message, *args)


def get_battery_stats() -> dict[str, str] | None:
    """
    Read MacOS battery stats with ioreg.
    """

    battery_keys = ('IsCharging', 'ExternalConnected', 'CurrentCapacity', 'MaxCapacity')
    battery_data = {}
    try:
        out = check_output(['ioreg', '-rc', 'AppleSmartBattery'], text=True)

        for line in out.splitlines():
            for key in battery_keys:
                if f'"{key}"' in line:
                    battery_data[key] = line.split('=')[-1].strip()
                    if len(battery_data) == len(battery_keys):
                        return battery_data

    except (FileNotFoundError, CalledProcessError, KeyError, ValueError):
        return None


def get_battery_cells(battery_data: dict[str, str]) -> list[tuple[int, str]]:
    _log("get_battery_cells(): Received", battery_data)
    cur_cap = int(battery_data.get('CurrentCapacity', 0))
    max_cap = int(battery_data.get('MaxCapacity', 100))
    percent = round(cur_cap * 100 / max_cap) if max_cap else 0

    is_charging = battery_data.get('IsCharging') == 'Yes'
    is_plugged = battery_data.get('ExternalConnected') == 'Yes'

    # discharging
    if not is_plugged and not is_charging:
        # TODO: declare the lambda once and don't repeat the code
        icon_color = UNPLUGGED_COLORS[
            min(UNPLUGGED_COLORS.keys(), key=lambda x: abs(x - percent))
        ]
        icon = UNPLUGGED_ICONS[
            min(UNPLUGGED_ICONS.keys(), key=lambda x: abs(x - percent))
        ]
    # plugged in and full
    elif is_plugged and not is_charging:
        icon_color = UNPLUGGED_COLORS[
            min(UNPLUGGED_COLORS.keys(), key=lambda x: abs(x - percent))
        ]
        icon = PLUGGED_ICONS[
            min(PLUGGED_ICONS.keys(), key=lambda x: abs(x - percent))
        ]
    # plugged in and charging
    else:
        icon_color = PLUGGED_COLORS[
            min(PLUGGED_COLORS.keys(), key=lambda x: abs(x - percent))
        ]
        icon = PLUGGED_ICONS[
            min(PLUGGED_ICONS.keys(), key=lambda x: abs(x - percent))
        ]
    percent_cell = (BATTERY_TEXT_FG, str(percent) + "% ")
    icon_cell = (icon_color, icon)
    return [percent_cell, icon_cell]


def _draw_icon(screen: Screen, index: int) -> int:
    if index != 1:
        return 0
    fg, bg = screen.cursor.fg, screen.cursor.bg
    screen.cursor.fg = ICON_FG
    screen.cursor.bg = ICON_BG
    screen.draw(BRAND_ICON)
    screen.cursor.fg, screen.cursor.bg = fg, bg
    screen.cursor.x = len(BRAND_ICON)
    return screen.cursor.x


def _draw_tabs(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_title_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    if screen.cursor.x >= screen.columns - len_info_cells:
        return screen.cursor.x

    tab_bg = screen.cursor.bg
    tab_fg = screen.cursor.fg
    default_bg = as_rgb(int(draw_data.default_bg))
    if extra_data.next_tab:
        next_tab_bg = as_rgb(draw_data.tab_bg(extra_data.next_tab))
        needs_soft_separator = next_tab_bg == tab_bg
    else:
        next_tab_bg = default_bg
        needs_soft_separator = False

    screen.cursor.x
    screen.draw(" ")
    screen.cursor.bg = tab_bg

    draw_title(draw_data, screen, tab, index)

    if needs_soft_separator:
        prev_fg = screen.cursor.fg
        if tab_bg == tab_fg:
            screen.cursor.fg = default_bg
        elif tab_bg != default_bg:
            c1 = draw_data.inactive_bg.contrast(draw_data.default_bg)
            c2 = draw_data.inactive_bg.contrast(draw_data.inactive_fg)
            if c1 < c2:
                screen.cursor.fg = default_bg
        screen.draw(" " + SOFT_SEPARATOR_SYMBOL)
        screen.cursor.fg = prev_fg 
    else:
        screen.draw(" ")
        screen.cursor.fg = tab_bg
        screen.cursor.bg = next_tab_bg
        screen.draw(SEPARATOR_SYMBOL)

    return screen.cursor.x


def _draw_info(screen: Screen, is_last: bool, cells: list[tuple[int, str]]) -> int:
    if not is_last:
        return 0

    draw_attributed_string(Formatter.reset, screen)
    screen.cursor.x = screen.columns - len_info_cells
    screen.cursor.fg = 0

    for (color, status) in cells:
        screen.cursor.fg = color
        screen.draw(status)
    screen.cursor.bg = 0

    return screen.cursor.x


def _redraw_tab_bar(_):
    _log("_redraw_tab_bar(): Calling refresh_active_tab_bar()")
    print(get_boss().active_tab_manager)
    get_boss().refresh_active_tab_bar()


def draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_title_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    global timer_id
    global len_info_cells
    global cached_battery_cells
    global cached_battery_cells_updated_at

    if timer_id is None and USE_REPAINT_TIMER is True:
        _log("draw_tab(): Registering repaint timer with interval", REFRESH_TIME)
        timer_id = add_timer(_redraw_tab_bar, REFRESH_TIME, True)

    cells = []

    # Throttle battery cell updates to every 2s
    if time() - cached_battery_cells_updated_at > 2:
        battery_stats = get_battery_stats()
        if battery_stats is not None:
            cached_battery_cells = get_battery_cells(battery_stats)
            cached_battery_cells_updated_at = time()

    if cached_battery_cells is not None:
        cells.extend(cached_battery_cells)

    time_str = datetime.now().strftime(" %H:%M")
    cells.append((TIME_FG, time_str))

    date_str = datetime.now().strftime(" %m/%d/%Y")
    cells.append((DATE_FG, date_str))

    len_info_cells = RIGHT_MARGIN
    for cell in cells:
        len_info_cells += len(str(cell[1]))

    _draw_icon(screen, index)
    _draw_tabs(
        draw_data,
        screen,
        tab,
        before,
        max_title_length,
        index,
        is_last,
        extra_data,
    )
    _draw_info(screen, is_last, cells)

    return screen.cursor.x
