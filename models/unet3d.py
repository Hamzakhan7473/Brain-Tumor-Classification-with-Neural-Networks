"""
3D U-Net for brain tumor segmentation (BraTS-style multimodal input).
Encoder–decoder with skip connections; softmax over classes per voxel.
"""
from tensorflow import keras
from tensorflow.keras import layers


def conv_block(x, filters, name_prefix):
    x = layers.Conv3D(filters, 3, padding="same", name=f"{name_prefix}_conv1")(x)
    x = layers.BatchNormalization(name=f"{name_prefix}_bn1")(x)
    x = layers.Activation("relu", name=f"{name_prefix}_relu1")(x)
    x = layers.Conv3D(filters, 3, padding="same", name=f"{name_prefix}_conv2")(x)
    x = layers.BatchNormalization(name=f"{name_prefix}_bn2")(x)
    x = layers.Activation("relu", name=f"{name_prefix}_relu2")(x)
    return x


def build_unet_3d(
    input_shape=(96, 96, 96, 4),
    num_classes=4,
    base_filters=32,
    depth=4,
    name="unet_3d",
):
    """
    Build 3D U-Net (BraTS-style: 4 MRI modalities as input channels).

    Parameters
    ----------
    input_shape : (D, H, W, C) e.g. (96,96,96,4) for FLAIR, T1, T1ce, T2.
    num_classes : voxels classified as background + tumor labels (BraTS remap → 4).
    base_filters : filters at the highest-resolution encoder level.
    depth : number of encoder levels (each halves spatial size).
    """
    inputs = keras.Input(shape=input_shape, name="input")

    skips = []
    skip_channels = []
    x = inputs
    ch = base_filters

    for i in range(depth):
        x = conv_block(x, ch, f"enc{i}")
        skips.append(x)
        skip_channels.append(ch)
        x = layers.MaxPooling3D(2, name=f"pool{i}")(x)
        ch = min(ch * 2, 512)

    x = conv_block(x, ch, "bottleneck")

    for i in range(depth - 1, -1, -1):
        target_ch = skip_channels[i]
        x = layers.UpSampling3D(2, name=f"up{depth - 1 - i}")(x)
        x = layers.Conv3D(target_ch, 2, padding="same", name=f"upconv{depth - 1 - i}")(x)
        x = layers.concatenate([x, skips[i]], axis=-1, name=f"skip_concat{i}")
        x = conv_block(x, target_ch, f"dec{i}")

    outputs = layers.Conv3D(num_classes, 1, padding="same", activation="softmax", name="seg_head")(x)

    return keras.Model(inputs=inputs, outputs=outputs, name=name)
