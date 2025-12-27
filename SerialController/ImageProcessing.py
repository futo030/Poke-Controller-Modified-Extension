# for compatibility
from pokecontrollerext.api.v0_1_8.image_processing import (  # noqa
    crop_image as crop_image,
    crop_image_extend as crop_image_extend,
    getInterframeDiff as getInterframeDiff,
    getImage as getImage,
    doPreprocessImage as doPreprocessImage,
    openImage as opneImage, # noqa 元の実装がtypoしてる
    ImageProcessing as ImageProcessing,
)
