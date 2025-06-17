import logging
logger = logging.getLogger(__name__)


def add_to_google_calendar(bildirishnoma):
    """
    Mock function to simulate adding a notification to Google Calendar.
    In a real implementation, this would use Google Calendar API.
    """
    try:
        event = {
            'summary': f"To'lov eslatmasi: {bildirishnoma.chiqim.xaridor.ism_familiya}",
            'description': f"Chiqim: {bildirishnoma.chiqim.truck.make} {bildirishnoma.chiqim.truck.model}\nSumma: {bildirishnoma.chiqim.oyiga_tolov}\nIzoh: {bildirishnoma.chiqim.izoh or 'Izoh yo`/q'}",
            'start': {'date': str(bildirishnoma.tolov_sana)},
            'end': {'date': str(bildirishnoma.tolov_sana)},
        }
        logger.info(f"Mock Google Calendar event created: {event}")
        return True
    except Exception as e:
        logger.error(f"Error adding to Google Calendar: {str(e)}")
        return False