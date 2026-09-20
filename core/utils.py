def get_country_code(request):
    code = request.headers.get("CF-IPCountry", "").strip().upper()

    if code in {"XX", "T1"}:
        return ""

    if len(code) != 2 or not code.isascii() or not code.isalpha():
        return ""

    return code