def check_positive_number(val):
    # Check if it's an instance of int or float
    if isinstance(val, (int, float)) and val > 0:
        if isinstance(val, int) or val.is_integer():
            return True
        else:
            return True
    return False


def validate_parameters(name, dob, lat, lon):
    if name and name.strip():
        if dob and dob.strip():
            if check_positive_number(lat):
                if check_positive_number(lon):
                    return True
                else:
                    return "Please enter a valid longitude 😭!! to proceed..."
            else:
                return "Please enter a valid latitude 😭!! to proceed..."

        else:
            return "Please enter your date of birth 😭!! to proceed..."

    else:
        return "Please enter your name 😭!! to proceed..."
