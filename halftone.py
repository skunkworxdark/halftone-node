# Copyright (c) 2023 Jonathan S. Pollack (https://github.com/JPPhoto)
# Halftoning implementation via Bohumir Zamecnik (https://github.com/bzamecnik/halftone/)

import random
from typing import Optional, Callable, Tuple

import numpy as np
from PIL import Image
from pydantic import BaseModel

from invokeai.app.invocations.baseinvocation import (
    BaseInvocation,
    BaseInvocationOutput,
    InputField,
    InvocationContext,
    OutputField,
    invocation,
)
from invokeai.app.invocations.primitives import ImageField, ImageOutput
from invokeai.app.models.image import ImageCategory, ResourceOrigin


@invocation("halftone", title="Halftone", tags=["halftone"], version="1.0.0")
class HalftoneInvocation(BaseInvocation):
    """Halftones an image"""

    image: ImageField = InputField(description="The image to halftone", default=None)
    spacing: float = InputField(gt=0, le=800, description="Halftone dot spacing", default=8)
    angle: float = InputField(ge=0, lt=360, description="Halftone angle", default=45)

    def pil_from_array(self, arr):
        return Image.fromarray((arr * 255).astype("uint8"))

    def array_from_pil(self, img):
        return np.array(img) / 255

    def evaluate_2d_func(self, img_shape, fn):
        w, h = img_shape
        xaxis, yaxis = np.arange(w), np.arange(h)
        return fn(xaxis[:, None], yaxis[None, :])

    def rotate(self, x: float, y: float, angle: float) -> Tuple[float, float]:
        """
        Rotate coordinates (x, y) by given angle.

        angle: Rotation angle in degrees
        """
        angle_rad = 2 * np.pi * angle / 360
        sin, cos = np.sin(angle_rad), np.cos(angle_rad)
        return x * cos - y * sin, x * sin + y * cos

    def euclid_dot(self, spacing: float, angle: float) -> Callable[[int, int], float]:
        pixel_div = 2.0 / spacing

        def func(x: int, y: int):
            x, y = self.rotate(x * pixel_div, y * pixel_div, angle)
            return 0.5 - (0.25 * (np.sin(np.pi * (x + 0.5)) + np.cos(np.pi * y)))

        return func

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)
        mode = image.mode

        image = image.convert("L")
        image = self.array_from_pil(image)
        halftoned = image > self.evaluate_2d_func(image.shape, self.euclid_dot(self.spacing, self.angle))
        halftoned = self.pil_from_array(halftoned)

        if mode == "RGBA":
            image = halftoned.convert("RGBA")
        else:
            image = halftoned.convert("RGB")

        image_dto = context.services.images.create(
            image=image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
            metadata=None,
            workflow=self.workflow,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image.width,
            height=image.height,
        )