import math

from video_processing.banner import (
    BannerRenderConfig,
    MIN_FONT_SIZE,
    compute_banner_height,
    generate_banner_image,
)


def _render_banner(text: str, video_width: int = 1280, video_height: int = 720):
    config = BannerRenderConfig(
        text=text,
        video_width=video_width,
        video_height=video_height,
        use_gradient=False,
        solid_color="#000000",
        gradient_start="#000000",
        gradient_end="#000000",
        font_color="#FFFFFF",
        font_path=None,
    )
    return generate_banner_image(config)


def test_short_text_retains_target_font_size():
    video_width = 1280
    video_height = 720
    font_scale = 0.45
    banner_height = compute_banner_height(video_height)
    target_font_size = max(18, int(round(banner_height * font_scale)))

    result = _render_banner("Short title", video_width=video_width, video_height=video_height)

    assert result.font_size >= target_font_size
    assert result.text_width <= math.ceil(video_width * 0.9)
    assert result.text_height <= math.ceil(banner_height * 0.9)


def test_long_text_wraps_and_respects_bounds():
    video_width = 1280
    video_height = 720
    font_scale = 0.45
    banner_height = compute_banner_height(video_height)
    min_font_scale = max(0.1, min(font_scale * 0.5, font_scale))
    min_font_size = max(MIN_FONT_SIZE, int(round(banner_height * min_font_scale)))

    long_text = " ".join(["Lorem ipsum dolor sit amet"] * 6)
    result = _render_banner(long_text, video_width=video_width, video_height=video_height)

    assert result.line_count >= 2
    assert result.font_size >= min_font_size
    assert result.text_width <= math.ceil(video_width * 0.9)
    assert result.text_height <= math.ceil(banner_height * 0.9)


def test_custom_height_and_font_scale():
    video_width = 1920
    video_height = 1080
    height_ratio = 0.3
    font_scale = 0.75

    base_config = BannerRenderConfig(
        text="Hi",
        video_width=video_width,
        video_height=video_height,
        use_gradient=False,
        solid_color="#000000",
        gradient_start="#000000",
        gradient_end="#000000",
        font_color="#FFFFFF",
    )

    custom_config = BannerRenderConfig(
        text="Hi",
        video_width=video_width,
        video_height=video_height,
        use_gradient=True,
        solid_color="#101010",
        gradient_start="#202020",
        gradient_end="#303030",
        font_color="#FFFFFF",
        height_ratio=height_ratio,
        font_scale=font_scale,
    )

    default_result = generate_banner_image(base_config)
    custom_result = generate_banner_image(custom_config)
    expected_height = compute_banner_height(video_height, height_ratio=height_ratio)

    assert custom_result.image.height == expected_height
    assert custom_result.image.height > default_result.image.height
    assert custom_result.font_size > default_result.font_size
