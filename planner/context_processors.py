from datetime import date


def site(request):
    return {
        "site_name": "TripCraft AI",
        "site_tagline": "Your journey, intelligently planned.",
        "site_author": "Karthik Aravind M",
        "year": date.today().year,
    }
