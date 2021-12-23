def redact_config_dict(data):
    """
    This function redacts secret values in the configuration dict.
    This prevents that logging prints plain api keys.
    """
    for key, value in data.items():
        # Redact the secret values
        if key == "api_key" and data[key]:
            data[key] = "<REDACTED>"

        # Check if there are still more dicts to loop over
        if isinstance(value, dict):
            redact_config_dict(value)

    return data
