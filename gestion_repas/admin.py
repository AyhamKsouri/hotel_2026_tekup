from django.contrib import admin

from .models import Menu, StockProduct

admin.site.register([Menu, StockProduct])
