from excludarr.modules.justwatch import JustWatch


def get_jw_providers_form_choices():
    jw_client = JustWatch()
    jw_locales = []

    for locale in jw_client.get_locales():
        jw_locales.append((locale,locale))
        
    return tuple(jw_locales)
