from common.config import normalize_dd_site


def test_normalize_dd_site() -> None:
    assert normalize_dd_site("us5") == "us5.datadoghq.com"
    assert normalize_dd_site("https://app.us5.datadoghq.com") == "us5.datadoghq.com"
    assert normalize_dd_site("api.us5.datadoghq.com") == "us5.datadoghq.com"
    assert normalize_dd_site("datadoghq.com") == "datadoghq.com"
    assert normalize_dd_site("eu") == "datadoghq.eu"
