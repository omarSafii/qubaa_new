from django.apps import AppConfig


class HalaqasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'halaqas'



class HalaqasConfig(AppConfig):
    name = 'halaqas'
    
    def ready(self):
        import halaqas.signals  # مهم!
        
        
        
        
        