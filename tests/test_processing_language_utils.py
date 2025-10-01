from processing.language_utils import (
    attempt_translate_text,
    infer_language_code_from_filename,
    normalize_language_code,
)


def test_normalize_language_code_handles_aliases():
    assert normalize_language_code("pt-br") == "PT"
    assert normalize_language_code("Français") == "FRAN"


def test_infer_language_code_from_filename_recognizes_suffix():
    assert infer_language_code_from_filename("video_final_en.mp4") == "ING"
    assert infer_language_code_from_filename("apresentacao_pt.mkv") == "PT"


def test_attempt_translate_text_returns_none_for_unknown_target():
    translated, changed = attempt_translate_text("Olá", "XXX")
    assert translated is None
    assert changed is False
