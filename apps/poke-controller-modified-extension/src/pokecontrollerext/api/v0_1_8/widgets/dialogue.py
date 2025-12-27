import glob
import json
import logging
import os
import tkinter as tk
import tkinter.ttk as ttk
from typing import Annotated, Any, Literal, TypeGuard, get_origin, overload

logger = logging.getLogger(__name__)

MessageMode0 = int | str | list[str]
CheckWidgetTypeName = Annotated[str, "check"]
CheckWidget = Annotated[
    list[CheckWidgetTypeName | str | bool],
    '["check", subtitle: str, init: bool]',
]
ComboWidgetTypeName = Annotated[str, "combo"]
ComboWidget = Annotated[
    list[ComboWidgetTypeName | str | list[str]],
    '["combo", subtitle: str, selectlist: list[str], init: str]',
]
EntryWidgetTypeName = Annotated[str, "entry"]
EntryWidget = Annotated[
    list[EntryWidgetTypeName | str],
    '["entry", subtitle: str, init: str]',
]
RadioWidgetTypeName = Annotated[str, "radio"]
RadioWidget = Annotated[
    list[RadioWidgetTypeName | str | list[str]],
    '["radio", subtitle: str, selectlist: list[str], init: str]',
]
SpinWidgetTypeName = Annotated[str, "spin"]
SpinWidget = Annotated[
    list[SpinWidgetTypeName | str | list[str]],
    '["spin", subtitle: str, selectlist: list[str], init: str]',
]
ScaleWidgetTypeName = Annotated[str, "scale"]
ScaleWidget = Annotated[
    list[ScaleWidgetTypeName | str | int | float],
    '["scale", subtitle: str, min: int | float, max: int | float, init: int | float, digit: int]',
]
NextWidgetTypeName = Annotated[str, "next"]
NextWidget = Annotated[list[NextWidgetTypeName], '["next"]']
WidgetTypeName = (
    str  # Literal["check", "combo", "entry", "radio", "spin", "scale", "next"]
)
Widget = (
    CheckWidget
    | ComboWidget
    | EntryWidget
    | RadioWidget
    | SpinWidget
    | ScaleWidget
    | NextWidget
)
MessageMode1 = list[Widget]
Message = MessageMode0 | MessageMode1


def is_widget(value: Any) -> TypeGuard[Widget]:
    if isinstance(value, list):
        return False
    return any(
        check(value)
        for check in (
            is_check_widget,
            is_combo_widget,
            is_entry_widget,
            is_radio_widget,
            is_spin_widget,
            is_scale_widget,
            is_next_widget,
        )
    )


def is_message_mode0(message: Message) -> TypeGuard[MessageMode0]:
    if isinstance(message, int):
        return True
    if isinstance(message, str):
        return True
    return isinstance(message, list) and all(isinstance(m, str) for m in message)


def is_message_mode1(message: Message) -> TypeGuard[MessageMode1]:
    if not isinstance(message, list):
        return False

    return any(is_widget(widget) for widget in message)


def is_widget_type(
    value: Any,
    widget_type: WidgetTypeName,
) -> bool:
    return isinstance(value, str) and value.casefold() == widget_type.casefold()


def is_check_widget(widget: Any) -> TypeGuard[CheckWidget]:
    if not isinstance(widget, list) or len(widget) != 3:
        return False

    name, subtitle, init = widget
    if not is_widget_type(name, "check"):
        return False
    if not isinstance(subtitle, str):
        return False
    return isinstance(init, bool)


def parse_check_widget(widget: CheckWidget) -> tuple[str, str, bool]:
    return tuple(widget)  # type: ignore[return-value]


def is_combo_widget(widget: Any) -> TypeGuard[ComboWidget]:
    if not isinstance(widget, list) or len(widget) != 4:
        return False

    name, subtitle, selectlist, init = widget
    if not is_widget_type(name, "combo"):
        return False
    if not isinstance(subtitle, str):
        return False
    if not isinstance(selectlist, list):
        return False
    if any(not isinstance(item, str) for item in selectlist):
        return False
    return isinstance(init, str)


def parse_combo_widget(widget: ComboWidget) -> tuple[str, str, list[str], str]:
    return tuple(widget)  # type: ignore[return-value]


def is_entry_widget(widget: Any) -> TypeGuard[EntryWidget]:
    if not isinstance(widget, list) or len(widget) != 3:
        return False

    name, subtitle, init = widget
    if not is_widget_type(name, "entry"):
        return False
    if not isinstance(subtitle, str):
        return False
    return isinstance(init, str)


def parse_entry_widget(widget: EntryWidget) -> tuple[str, str, str]:
    return tuple(widget)  # type: ignore[return-value]


def is_radio_widget(widget: Any) -> TypeGuard[RadioWidget]:
    if isinstance(widget, list) or len(widget) != 4:
        return False

    name, subtitle, selectlist, init = widget
    if not is_widget_type(name, "radio"):
        return False
    if not isinstance(subtitle, str):
        return False
    if not isinstance(selectlist, list):
        return False
    if any(not isinstance(item, str) for item in selectlist):
        return False
    return isinstance(init, str)


def parse_radio_widget(widget: RadioWidget) -> tuple[str, str, list[str], str]:
    return tuple(widget)  # type: ignore[return-value]


def is_spin_widget(widget: Any) -> TypeGuard[SpinWidget]:
    if not isinstance(widget, list) or len(widget) != 4:
        return False

    name, subtitle, selectlist, init = widget
    if not is_widget_type(name, "spin"):
        return False
    if not isinstance(subtitle, str):
        return False
    if not isinstance(selectlist, list):
        return False
    if any(not isinstance(item, str) for item in selectlist):
        return False
    return isinstance(init, str)


def parse_spin_widget(widget: SpinWidget) -> tuple[str, str, list[str], str]:
    return tuple(widget)  # type: ignore[return-value]


def is_scale_widget(widget: Any) -> TypeGuard[ScaleWidget]:
    if not isinstance(widget, list) or len(widget) != 6:
        return False

    name, subtitle, min_value, max_value, init, digit = widget
    if not is_widget_type(name, "scale"):
        return False
    if not isinstance(subtitle, str):
        return False
    if not isinstance(min_value, (int, float)):
        return False
    if not isinstance(max_value, (int, float)):
        return False
    if not isinstance(init, (int, float)):
        return False
    return isinstance(digit, int)


def parse_scale_widget(
    widget: ScaleWidget,
) -> tuple[str, str, int | float, int | float, int | float, int]:
    return tuple(widget)  # type: ignore[return-value]


def is_next_widget(widget: Any) -> TypeGuard[NextWidget]:
    return isinstance(widget, str) and widget.casefold() == "next".casefold()


class PokeConDialogue:
    def __init__(
        self,
        parent: tk.Toplevel,
        title: str,
        message: Message,
        desc: str | None = None,
        mode: int = 0,
        pos: int = 2,
    ) -> None:
        """
        pokecon用ダイアログ生成関数(注意:mode=0と1でmessageの取り扱いが大きく異なる。)
        mode | int: 0のときEntryのみ、1のとき6種類のwidgetに対応
        pos | int: OK/Cancelの位置(1のときTOP、2のときBOTTOM、3のときBOTH)
        title | str: タイトル
        message | mode=0の場合 : int/str/list: Entryのラベル、mode=1の場合 : list[widget, widget, ...]: widgetごとの設定をリスト化したもの
        widget | list : widgetごとの設定(ウィジェットの種類によってリストの中身は異なる。以下を参照。)
        checkbox/entryの場合 : [type, subtitle, init] (例) ["check", "Check(例)", True]、["ENTRY", "Entry(例)", "初期値"]
        combobox/radiobutton/spinboxの場合 : [type, subtitle, selectlist, init] (例) ["Combo", "Combo(例)", ["hello", "world"], "hello"]、["RADIO", "Radio(例)", ["dog", "cat"],"dog"]、["Spin", "Spin(例)", list(map(str, range(10))), "3"]
        scaleの場合 : [type, subtitle, min, max, init, digit] (例) ["Scale", "scale(例)", 0, 100, 50.1, 2]
        type | str: widgetの種類(check/combo/entry/radio/spin/scaleのいずれか。大文字小文字は問わない)
        subtitle | str : widgetのタイトル
        init | checkboxの場合bool,scaleの場合int/float,その他str : 初期値
        selectlist | list : 項目のリスト
        min/max | int/float : scaleの最小値と最大値
        digit | int : 有効桁数
        return : なし
        """
        self._ls: list[bool | int | float | str] | None = None
        self.isOK: bool = False

        self.message_dialogue = parent
        self.message_dialogue.title(title)
        self.message_dialogue.attributes("-topmost", True)
        self.message_dialogue.protocol("WM_DELETE_WINDOW", self.close_window)

        self.main_frame = tk.Frame(self.message_dialogue)

        description = desc if desc is not None else title
        self.description_label = ttk.Label(
            self.main_frame, text=description, anchor="center"
        )
        self.description_label.grid(
            column=0, columnspan=2, ipadx="10", ipady="10", row=0, sticky="nsew"
        )

        cnt = 1
        if pos in [1, 3]:
            self.result = ttk.Frame(self.main_frame)
            self.OK = ttk.Button(self.result, command=self.ok_command)
            self.OK.configure(text="OK")
            self.OK.grid(column=0, row=1, padx=5, pady=5)
            self.Cancel = ttk.Button(self.result, command=self.cancel_command)
            self.Cancel.configure(text="Cancel")
            self.Cancel.grid(column=1, row=1, sticky="ew", padx=5, pady=5)
            self.result.grid(column=0, columnspan=2, pady=5, row=cnt, sticky="ew")
            self.result.grid_anchor("center")
            cnt += 1

        self.inputs = ttk.Frame(self.main_frame)

        self.dialogue_ls: dict[
            str, tk.BooleanVar | tk.IntVar | tk.DoubleVar | tk.StringVar
        ] = {}
        x = self.message_dialogue.master.winfo_x()
        w = self.message_dialogue.master.winfo_width()
        y = self.message_dialogue.master.winfo_y()
        h = self.message_dialogue.master.winfo_height()
        w_ = self.message_dialogue.winfo_width()
        h_ = self.message_dialogue.winfo_height()
        self.message_dialogue.geometry(
            f"+{int(x + w / 2 - w_ / 2)}+{int(y + h / 2 - h_ / 2)}"
        )

        if mode == 0 and is_message_mode0(message):
            self.mode0(message)
        elif mode == 1 and is_message_mode1(message):
            self.mode1(message)

        self.inputs.grid(
            column=0, columnspan=2, ipadx="10", ipady="10", row=cnt, sticky="nsew"
        )
        self.inputs.grid_anchor("center")
        cnt += 1

        if pos in [2, 3]:
            self.result2 = ttk.Frame(self.main_frame)
            self.OK2 = ttk.Button(self.result2, command=self.ok_command)
            self.OK2.configure(text="OK")
            self.OK2.grid(column=0, row=1, padx=5, pady=5)
            self.Cancel2 = ttk.Button(self.result2, command=self.cancel_command)
            self.Cancel2.configure(text="Cancel")
            self.Cancel2.grid(column=1, row=1, sticky="ew", padx=5, pady=5)
            self.result2.grid(column=0, columnspan=2, pady=5, row=cnt, sticky="ew")
            self.result2.grid_anchor("center")

        self.main_frame.pack()
        self.message_dialogue.master.wait_window(self.message_dialogue)

    # FIXME: あとでdocstringを書き直す
    def mode0(self, message: int | str | list[str]) -> None:
        """dialogue_lsにStringVarを追加して、それに紐づいたlabelとentryを生成して配置する"""
        if isinstance(message, int):
            messages = [str(message)]
        elif isinstance(message, str):
            messages = [message]
        else:
            messages = message

        for i, msg in enumerate(messages):
            self.dialogue_ls[msg] = var = tk.StringVar()
            label = ttk.Label(self.inputs, text=msg)
            entry = ttk.Entry(self.inputs, textvariable=var)
            label.grid(column=0, row=i, sticky="nsew", padx=3, pady=3)
            entry.grid(column=1, row=i, sticky="nsew", padx=3, pady=3)

    # FIXME: あとでdocstringを書き直す
    def mode1(self, dialogue_list: MessageMode1) -> None:
        labelframes: list[ttk.Labelframe | None] = []

        # scaleの値を表示するlabelを格納するリスト
        scale_label_list: list[tk.Label] = []
        # scaleが何番目のwidgetなのかを格納するリスト
        scale_index_list: list[int] = []
        # scaleの有効桁数を格納するリスト
        scale_digit_list: list[int] = []

        def change_scale_value(
            event: str,  # noqa
        ) -> None:  # scaleのバーを動かしたときにlabelの値を変更するための関数
            for i, (index, fmt) in enumerate(zip(scale_index_list, scale_digit_list)):
                widget = dialogue_list[index]
                if not is_spin_widget(widget):
                    return
                _, subtitle, selectlist, init = parse_spin_widget(widget)
                label = scale_label_list[i]
                var: tk.DoubleVar = self.dialogue_ls[subtitle]  # type: ignore[assignment]
                value = var.get()
                if fmt != 0:
                    label["text"] = val = round(value, fmt)
                    var.set(val)
                else:
                    label["text"] = value

        column0 = 0
        row0 = 0
        for i, widget in enumerate(dialogue_list):
            if is_next_widget(widget):
                labelframes.append(None)
                column0 += 1
                row0 = 0
            else:
                # widgetはすべてframeの中に入れる。scaleの場合、値を示すlabelもフレームの中に入れる。
                labelframe = ttk.Labelframe(self.inputs, text=widget[1])  # type: ignore[arg-type]
                labelframes.append(labelframe)

                # Checkbox
                if is_check_widget(widget):
                    _, subtitle, check_init = parse_check_widget(widget)
                    self.dialogue_ls[subtitle] = check_var = tk.BooleanVar(
                        value=check_init
                    )
                    checkbutton = ttk.Checkbutton(labelframe, variable=check_var)
                    checkbutton.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)
                # Combobox
                elif is_combo_widget(widget):
                    _, subtitle, selectlist, combo_init = parse_combo_widget(widget)
                    text_length = 10
                    for name in selectlist:
                        if text_length < len(str(name)) + 5:
                            text_length = len(str(name)) + 5
                    self.dialogue_ls[subtitle] = combo_var = tk.StringVar(
                        value=combo_init
                    )
                    combobox = ttk.Combobox(
                        labelframe,
                        values=selectlist,
                        textvariable=combo_var,
                        width=text_length,
                        state="readonly",
                    )
                    combobox.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)
                # Entry
                elif is_entry_widget(widget):
                    _, subtitle, entry_init = parse_entry_widget(widget)
                    self.dialogue_ls[subtitle] = entry_var = tk.StringVar(
                        value=entry_init
                    )
                    entry = ttk.Entry(labelframe, textvariable=entry_var)
                    entry.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)
                # Radiobutton
                elif is_radio_widget(widget):
                    _, subtitle, selectlist, radio_init = parse_radio_widget(widget)
                    self.dialogue_ls[subtitle] = radio_var = tk.StringVar(
                        value=radio_init
                    )
                    for j, text0 in enumerate(selectlist):
                        radiobutton = ttk.Radiobutton(
                            labelframe,
                            text=text0,
                            variable=radio_var,
                            value=text0,
                        )
                        radiobutton.grid(column=j, row=0, sticky="nsew", padx=3, pady=3)
                # Scale
                elif is_scale_widget(widget):
                    _, subtitle, min_value, max_value, scale_init, digit = (
                        parse_scale_widget(widget)
                    )
                    scale_index_list.append(i)
                    scale_digit_list.append(digit)
                    spin_var: tk.IntVar | tk.DoubleVar
                    if digit != 0:  # 浮動小数点数
                        self.dialogue_ls[subtitle] = spin_var = tk.DoubleVar(
                            value=scale_init
                        )
                        scale_label_list.append(
                            tk.Label(
                                labelframe,
                                width=10,
                                text="%s"
                                % round(
                                    spin_var.get(),
                                    digit,
                                ),
                            )
                        )
                    else:  # 整数
                        self.dialogue_ls[subtitle] = spin_var = tk.IntVar(
                            value=int(scale_init)
                        )
                        scale_label_list.append(
                            tk.Label(
                                labelframe,
                                width=10,
                                text="%s" % self.dialogue_ls[subtitle].get(),
                            )
                        )
                    scale = ttk.Scale(
                        labelframe,
                        from_=min_value,
                        to=max_value,
                        variable=spin_var,
                        command=change_scale_value,
                    )
                    scale_label_list[-1].grid(
                        column=0, row=0, sticky="nsew", padx=3, pady=3
                    )
                    scale.grid(column=1, row=0, sticky="nsew", padx=3, pady=3)
                # Spinbox
                elif is_spin_widget(widget):
                    _, subtitle, selectlist, spin_init = parse_spin_widget(widget)
                    self.dialogue_ls[subtitle] = tk.StringVar(value=spin_init)
                    spinbox = ttk.Spinbox(
                        labelframe,
                        values=selectlist,
                        textvariable=self.dialogue_ls[subtitle],
                    )
                    spinbox.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)

                labelframe.grid(column=column0, row=row0, sticky="nsew", padx=3, pady=3)
                row0 += 1

        # widgetのサイズをフレームのサイズに合わせる
        for widget, f in zip(dialogue_list, labelframes):
            if widget is None or f is None:
                continue

            if is_next_widget(widget):
                pass
            else:
                if is_scale_widget(widget):
                    f.grid_columnconfigure(0, weight=1)
                    f.grid_columnconfigure(1, weight=3)
                elif not is_radio_widget(widget):
                    f.grid_columnconfigure(0, weight=1)
                else:
                    pass

    @overload
    def ret_value(
        self,
        need: type[list],
    ) -> list[bool | int | float | str] | Literal[False] | None: ...

    @overload
    def ret_value(
        self,
        need: type[dict],
    ) -> dict[str, bool | int | float | str] | Literal[False]: ...

    def ret_value(
        self,
        need: type[list] | type[dict],
    ) -> (
        list[bool | int | float | str]
        | dict[str, bool | int | float | str]
        | Literal[False]
        | None
    ):
        if self.isOK:
            origin = get_origin(need) or need
            if origin is dict:  # needは型なのでisinstanceは使えない
                return {k: v.get() for k, v in self.dialogue_ls.items()}
            elif origin is list:  # needは型なのでisinstanceは使えない
                return self._ls
            else:
                logger.warning("Wrong arg. Try Return list.")
                return self._ls
        else:
            return False

    def close_window(self) -> None:
        self.message_dialogue.destroy()
        self.isOK = False

    def ok_command(self) -> None:
        self._ls = [v.get() for v in self.dialogue_ls.values()]
        self.message_dialogue.destroy()
        self.isOK = True

    def cancel_command(self) -> None:
        self.message_dialogue.destroy()
        self.isOK = False


def check_widget_name(dialogue_list: list, except_name: list | None = None) -> bool:
    """
    ウィジェットに同一名称がないかを確認
    """
    if except_name is None:
        except_name = []

    input_name = [
        setting[1] for setting in dialogue_list if len(setting) > 1
    ] + except_name
    checked_name = []
    output_name = [name for name in input_name]
    for name in output_name:
        if name not in checked_name:
            checked_name.append(name)

    return len(input_name) == len(output_name)


def get_setting(filename: str | None) -> Any:
    """
    保存した設定値を読み込む
    """
    if filename is None:
        return None
    try:
        with open(filename, encoding="utf-8") as f:
            file = json.load(f)
            return file
    except Exception:
        return None


def save_setting(filename: str, settings: dict) -> None:
    """
    設定値を保存する
    """
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


def generate_new_dialogue_list(
    dialogue_list: MessageMode1,
    filename: str | None,
) -> MessageMode1:
    settings = get_setting(filename)
    if not settings:
        return dialogue_list
    else:
        new_dialogue_list: MessageMode1 = []
        for setting in dialogue_list:
            if is_widget(setting):
                try:
                    setting[-1] = settings[setting[1]]
                except Exception:
                    pass
            new_dialogue_list.append(setting)
    return new_dialogue_list


def save_dialogue_settings(
    new_dialogue_list: MessageMode1,
    ret: list[bool | int | float | str] | dict[str, bool | int | float | str],
    filename: str,
) -> None:
    try:
        settings = {}
        if isinstance(ret, list):
            for n, setting in enumerate(new_dialogue_list):
                if not is_next_widget(setting):
                    settings[setting[1]] = ret[n]
            save_setting(filename, settings)
        else:
            save_setting(filename, ret)
    except Exception:
        logger.error("Error: Configuration dump failed.")


def get_settings_list(dirname: str) -> list:
    if os.path.isdir(dirname):
        pass
    else:
        os.makedirs(dirname)
    filename = os.path.join(dirname, "**", "*.json")
    settings_list = glob.glob(filename, recursive=True)

    len_pass = len(dirname) + 1
    settings_name_list = [
        file[len_pass:-5] for file in settings_list if file[len_pass] != "_"
    ]

    return settings_name_list
