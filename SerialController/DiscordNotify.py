from pokecontroller.core.image import RawImage, to_bytes
# for compatibility
from pokecontrollerext.api.v0_1_8.notification.discord import Discord_Notify as Discord_Notify  # noqa


# for compatibility
def convert_bgr_to_bytes(image_bgr: RawImage):
    """
    BGRの画像をbyte形式に変換する
    """
    return to_bytes(src=image_bgr, fmt="png")
