def test_package_import() -> None:
    import iaai

    assert iaai.__version__ == "0.0.1.dev0"
