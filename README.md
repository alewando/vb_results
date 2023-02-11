# vb_results
Scrapes volleyball schedules/results from AES, formats simply for change detection/notification

# Apache config
`/etc/apache2/conf-available/wsgi.conf`:
```
WSGIScriptAlias /vb_results /var/www/html/wsgi/vb_results/vb_results_app.wsgi
WSGIDaemonProcess alewando.com processes=2 threads=15
WSGIProcessGroup alewando.com
WSGIScriptReloading On

WSGIApplicationGroup %{GLOBAL}
<Directory /var/www/html/wsgi>
   WSGIApplicationGroup %{GLOBAL}
   Require all granted
</Directory>
```
Then:
```sudo a2enconf wsgi```

