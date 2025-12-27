from typing import Any

MAPPING: dict[str, Any] = {
    "general": {
        "version": "General Setting/version",
        "theme": "General Setting/theme",
    },
    "capture": {
        "camera_id": "General Setting/camera_id",
        "camera_name": "General Setting/camera_name",
        "fps": "General Setting/fps",
        "size": "General Setting/show_size",
        "show_realtime": "General Setting/is_show_realtime",
        "show_matched": "General Setting/is_show_value",
        "show_guide": "General Setting/is_show_guide",
    },
    "serial": {
        "port": "General Setting/com_port",
        "port_name": "General Setting/com_port_name",
        "baud_rate": "General Setting/baud_rate",
        "data_format": "General Setting/serial_data_format_name",
        "show_data": "General Setting/is_show_serial",
    },
    "device": {
        "touchscreen": {
            "sx": "General Setting/touchscreen_start_x",
            "sy": "General Setting/touchscreen_start_y",
            "ex": "General Setting/touchscreen_end_x",
            "ey": "General Setting/touchscreen_end_y",
        },
        "keyboard": {
            "enabled": "General Setting/is_use_keyboard",
            "keymap": {
                "button": {
                    "y": "KeyMap-Button/Button.Y",
                    "b": "KeyMap-Button/Button.B",
                    "x": "KeyMap-Button/Button.X",
                    "a": "KeyMap-Button/Button.A",
                    "l": "KeyMap-Button/Button.L",
                    "r": "KeyMap-Button/Button.R",
                    "zl": "KeyMap-Button/Button.ZL",
                    "zr": "KeyMap-Button/Button.ZR",
                    "minus": "KeyMap-Button/Button.MINUS",
                    "plus": "KeyMap-Button/Button.PLUS",
                    "lclick": "KeyMap-Button/Button.LCLICK",
                    "rclick": "KeyMap-Button/Button.RCLICK",
                    "home": "KeyMap-Button/Button.HOME",
                    "capture": "KeyMap-Button/Button.CAPTURE",
                },
                "direction": {
                    "up": "KeyMap-Direction/Direction.UP",
                    "right": "KeyMap-Direction/Direction.RIGHT",
                    "down": "KeyMap-Direction/Direction.DOWN",
                    "left": "KeyMap-Direction/Direction.LEFT",
                    "up_right": "KeyMap-Direction/Direction.UP_RIGHT",
                    "down_right": "KeyMap-Direction/Direction.DOWN_RIGHT",
                    "down_left": "KeyMap-Direction/Direction.DOWN_LEFT",
                    "up_left": "KeyMap-Direction/Direction.UP_LEFT",
                },
                "dpad": {
                    "up": "KeyMap-Hat/Hat.TOP",
                    "up_right": "KeyMap-Hat/Hat.TOP_RIGHT",
                    "right": "KeyMap-Hat/Hat.RIGHT",
                    "down_right": "KeyMap-Hat/Hat.BTM_RIGHT",
                    "down": "KeyMap-Hat/Hat.BTM",
                    "down_left": "KeyMap-Hat/Hat.BTM_LEFT",
                    "left": "KeyMap-Hat/Hat.LEFT",
                    "up_left": "KeyMap-Hat/Hat.TOP_LEFT",
                    "neutral": "KeyMap-Hat/Hat.CENTER",
                },
            },
        },
        "mouse": {
            "enabled_lclick": "General Setting/is_use_mouse_lclick",
            "enabled_rclick": "General Setting/is_use_mouse_rclick",
        },
        "pro_controller": {
            "enabled": "General Setting/is_use_pro_controller",
            "enabled_record": "General Setting/is_record_pro_controller",
        },
    },
    "command": {
        "shortcut": {
            "registered_commands": {
                "1": {
                    "klass": "Shortcut/command_class_1",
                    "name": "Shortcut/command_name_1",
                },
                "2": {
                    "klass": "Shortcut/command_class_2",
                    "name": "Shortcut/command_name_2",
                },
                "3": {
                    "klass": "Shortcut/command_class_3",
                    "name": "Shortcut/command_name_3",
                },
                "4": {
                    "klass": "Shortcut/command_class_4",
                    "name": "Shortcut/command_name_4",
                },
                "5": {
                    "klass": "Shortcut/command_class_5",
                    "name": "Shortcut/command_name_5",
                },
                "6": {
                    "klass": "Shortcut/command_class_6",
                    "name": "Shortcut/command_name_6",
                },
                "7": {
                    "klass": "Shortcut/command_class_7",
                    "name": "Shortcut/command_name_7",
                },
                "8": {
                    "klass": "Shortcut/command_class_8",
                    "name": "Shortcut/command_name_8",
                },
                "9": {
                    "klass": "Shortcut/command_class_9",
                    "name": "Shortcut/command_name_9",
                },
                "10": {
                    "klass": "Shortcut/command_class_10",
                    "name": "Shortcut/command_name_10",
                },
            },
        },
    },
    "notification": {
        "windows": {
            "enabled_started": "Notification/is_win_notification_start",
            "enabled_ended": "Notification/is_win_notification_end",
        },
        "line": {
            "enabled_started": "Notification/is_line_notification_start",
            "enabled_ended": "Notification/is_line_notification_end",
        },
        "discord": {
            "enabled_started": "Notification/is_discord_notification_start",
            "enabled_ended": "Notification/is_discord_notification_end",
        },
    },
    "widget": {
        "output": {
            "size_balance": "Output/area_size",
            "stdout": "Output/stdout_destination",
            "visible_output1": False,
            "visible_output2": False,
        },
        "software_controller": {
            "position": False,
            "visible": False,
        },
        "dialog": {
            "confirm_buttons_position": False,
        },
    },
}
