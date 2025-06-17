from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Xaridor
from chiqim.models import Chiqim, TolovTuri

# Quyidagi signalni olib tashlaymiz, chunki u rekursiyaga olib keladi
# @receiver(post_save, sender=Xaridor)
# def update_xaridor_financials(sender, instance, **kwargs):
#     instance.update_financials()

@receiver(post_save, sender=Chiqim)
@receiver(post_save, sender=TolovTuri)
@receiver(post_delete, sender=Chiqim)
@receiver(post_delete, sender=TolovTuri)
def update_xaridor_on_chiqim_change(sender, instance, **kwargs):
    if hasattr(instance, 'xaridor'):
        instance.xaridor.update_financials()