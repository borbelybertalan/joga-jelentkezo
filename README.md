# Jóga foglaló

FastAPI és SQLite alapú jógaóra-foglaló alkalmazás. A backend azonos originről szolgálja ki a statikus felületet, ezért az alkalmazást a `main:app` ASGI alkalmazásként kell indítani.

## Első indítás

1. Másold a `.env.example` fájlt `.env` néven.
2. Állíts be egyedi `ADMIN_USERNAME`, legalább 12 karakteres `ADMIN_PASSWORD` és legalább 32 karakteres véletlen `APP_SECRET` értéket.
3. Aktiváld a virtuális környezetet, majd indítsd el az alkalmazást:

   ```sh
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```

4. Nyisd meg a `http://127.0.0.1:8000/` címet. Az admin felület: `/admin.html`.

Az első indítás egyszeri, verziózott migrációt futtat. A régi, helyi magyar időként tárolt óraidőpontokat UTC-re alakítja, de nem módosítja az óra címét, oktatóját, megjegyzését vagy Zoom-beállítását.

## Konfiguráció

- `DATABASE_PATH`: opcionális abszolút SQLite fájlútvonal.
- `FRONTEND_ORIGINS`: csak akkor add meg vesszővel elválasztva, ha a frontend más originről fut. Az alapértelmezett, azonos originű kiszolgáláshoz nincs szükség CORS-ra.

## Ellenőrzések

```sh
python -m unittest discover -s tests -v
```

Az órarend feltöltése a következő 365 napra idempotensen futtatható:

```sh
python populate_db.py
```
