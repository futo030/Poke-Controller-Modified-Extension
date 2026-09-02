import cv2

from pokecontroller.core.image import RawImage


def show(image: RawImage, window_name: str = "image") -> None:
    cv2.imshow(window_name, image)
    cv2.waitKey(0)


def destroy_all_windows() -> None:
    cv2.destroyAllWindows()
