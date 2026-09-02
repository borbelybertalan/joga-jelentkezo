# Jóga foglaló – V1 teendőlista

**Állapot:** `Kész: 23 / 59`  
**Cél:** éles, vendégek által önállóan használható foglalási oldal.

## Prioritások

- **P0 – indulás előtt:** éles használathoz, biztonsághoz vagy jogszerű működéshez szükséges.
- **P1 – röviddel indulás után:** fontos használhatósági és üzemeltetési fejlesztés.
- **P2 – kényelmi fejlesztés:** értéknövelő, de az indulást nem akadályozza.

## Feladatgazdák

- **[Codex]**: fejlesztési, tesztelési és dokumentációs feladat; ezt meg tudom csinálni a projektben.
- **[Te]**: külső szolgáltatói, fiók-, domain- vagy üzleti döntés; ehhez a te közreműködésed kell.

## P0 – Indulás előtt

### Foglalási élmény

- [ ] **[Te]** Vásárolj domaint, és hozz létre legalább egy automatikus küldésre használható címet, például `jelentkezes@...`.
- [ ] **[Te]** Válassz és regisztrálj e-mail-küldő szolgáltatónál (például Brevo), majd add meg a technikai hozzáférést és a domain-hitelesítéshez szükséges DNS-beállításokat.
- [x] **[Codex]** Küldj e-mailes foglalási visszaigazolást az óra adataival és a lemondó linkkel.
- [x] **[Codex]** A visszaigazoló e-mailben jelenítsd meg a vendég bérletének típusát, lejáratát és – 8 alkalmas bérletnél – fennmaradó alkalmait.
- [ ] **[Codex]** Küldj e-mailes értesítést a várólistára kerülésről és a felszabadult helyről.
- [ ] **[Codex]** Ellenőrizd az e-mail-cím formátumát, és vezess be e-mailes megerősítést, hogy a megadott cím valóban a jelentkezőé legyen.
- [ ] **[Codex]** Jeleníts meg egységes, egyértelmű siker- és hibaüzeneteket a foglalási folyamat minden lépésében.
- [ ] **[Codex]** A már megtartott órákat szürkén jelenítsd meg a naptárban.
- [ ] **[Codex]** Megtartott órára kattintáskor csak azt az üzenetet mutasd, hogy arra az órára már nem lehet jelentkezni; ne nyisd meg a foglalási űrlapot.

### Bérletek és vendégazonosítás

- [x] **[Codex]** Készíts külön adminoldalt vagy adminszekciót az összes, korábban jelentkezett vendég egyszeri listázására.
- [x] **[Codex]** Új vendégnek azt tekintsd, aki olyan e-mail-címmel foglal, amely még nem szerepel az adatbázisban.
- [x] **[Codex]** Lehessen az adminnak egy vendéghez manuálisan havi vagy 8 alkalmas bérletet hozzáadnia.
- [x] **[Codex]** A havi bérletet a kiadásától számított 30 napig tedd érvényessé.
- [x] **[Codex]** A 8 alkalmas bérletet a kiadásától számított 60 napig tedd érvényessé, és kövesd a fennmaradó alkalmak számát.
- [x] **[Codex]** A 8 alkalmas bérletből csak akkor vonj le egy alkalmat, amikor a foglalás belép a 12 órás lemondási határidőbe.
- [x] **[Codex]** Szabályos, a 12 órás határidő előtti lemondáskor ne vonj le alkalmat; ha az alkalom már levonásra került, írd vissza.
- [x] **[Codex]** Bérlet nélkül is engedd a foglalást, de a foglaláskor és a visszaigazoló e-mailben jelezd, hogy a bérletet személyesen kell rendezni.
- [x] **[Codex]** Készíts adminos e-mail-összevonó funkciót: két e-mail-címet egy vendéghez lehessen kapcsolni.
- [x] **[Codex]** Összevont e-mail-címeknél bármelyik címről indított foglalást ugyanahhoz a vendéghez, bérlethez és előzményhez rendeld.
- [x] **[Codex]** Akadályozd meg, hogy az e-mail-összevonás duplikált vendéget, bérletet vagy foglalást hozzon létre.
- [x] **[Codex]** Egy órára kattintó admin számára jelezd minden jelentkezőnél, van-e aktív bérlete.
- [x] **[Codex]** Aktív bérletnél mutasd az adminnak a bérlet típusát, lejárati dátumát és – 8 alkalmas bérletnél – a fennmaradó alkalmakat.
- [x] **[Codex]** Írj teszteket a bérlet lejáratára, a 8 alkalom nyilvántartására és az e-mail-összevonásra.

### Adminisztráció

- [x] **[Codex]** Lehessen meglévő órát szerkeszteni: cím, időpont, létszám, oktató, megjegyzés és online elérhetőség.
- [x] **[Codex]** Óratörlés előtt mutasd meg a jelentkezők számát és a törlés következményeit.
- [x] **[Codex]** Tegyél az adminfelületre érthető munkamenet-lejárati és újrabelépési visszajelzést.

### Éles üzemeltetés

- [ ] **[Codex]** Rögzítsd az éles környezet szükséges titkait és környezeti változóit biztonságos konfigurációban.
- [ ] **[Te]** Válassz tárhelyszolgáltatót, állítsd be a saját domaint és HTTPS-tanúsítványt.
- [ ] **[Codex]** Készíts rendszeres adatbázismentési és visszaállítási folyamatot, majd próbáld is ki a visszaállítást.
- [ ] **[Codex]** Vezess be hibalogolást és ellenőrizhető egészségügyi végpontot az éles szolgáltatáshoz.

### Adatvédelem és jog

- [ ] Készíts és tegyél elérhetővé adatkezelési tájékoztatót.
- [ ] Készíts foglalási feltételeket, beleértve a lemondási határidőt és a várólista szabályait.
- [ ] Vezesd be a szükséges adatkezelési hozzájárulást a foglalási űrlapon.
- [ ] Határozd meg és dokumentáld a személyes adatok megőrzési, exportálási és törlési rendjét.

## P1 – Röviddel indulás után

### Mobil és hozzáférhetőség

- [ ] Teszteld a naptárt és a foglalási, lemondási, valamint admin modálokat kis képernyőn.
- [ ] Biztosíts teljes billentyűzetes vezérlést és látható fókuszjelzést.
- [ ] Kezeld a modálok fókuszát megnyitáskor, bezáráskor és `Escape` lenyomásakor.
- [ ] Egészítsd ki a mezőcímkéket, hibaüzeneteket és állapotjelzéseket akadálymentes leírásokkal.

### Működési szabályok

- [ ] Tárold óránként külön az óra hosszát a jelenlegi címhez kötött időtartam-szabály helyett.
- [ ] Adj lehetőséget ismétlődő órasorozatok létrehozására és kezelésére.
- [ ] Rögzíts oktatói, terem- és online-csatlakozási adatokat külön, következetes mezőkben.
- [ ] Határozd meg és érvényesítsd a létszám módosításának szabályait már meglévő foglalások mellett.
- [ ] Adj vendégoldali lehetőséget az óra naptárba mentésére.

### Minőségbiztosítás

- [ ] Készíts végponti teszteket a sikeres, hibás és várólistás foglalásra.
- [ ] Készíts végponti teszteket a lemondásra és a várólista automatikus előreléptetésére.
- [ ] Teszteld az admin bejelentkezést, óralétrehozást, szerkesztést és törlést.
- [ ] Kezeld és teszteld a hálózati hibákat, az időtúllépést és a nem értelmezhető szerverválaszokat.
- [ ] Készíts ellenőrzőlistát a támogatott böngészők és mobil eszközméretek manuális teszteléséhez.

### Helyi kereshetőség (SEO)

- [x] **[Codex]** A főoldal H1 címe legyen: „Iyengar jóga Pécs – órarend és foglalás”.
- [x] **[Codex]** Állíts be keresőbarát oldal címet és leírást: „Iyengar jóga Pécs | Órarend és foglalás”.
- [x] **[Codex]** Tegyél a naptár fölé vagy alá rövid, természetes bemutatkozó szöveget az Iyengar jógáról, a pécsi órákról és a jelentkezésről.
- [x] **[Te]** Add meg a pontos órahelyszínt vagy legalább a pécsi városrészt, hogy az felkerülhessen a kapcsolati részhez.
- [ ] **[Te]** Hozz létre és hitelesíts Google Cégprofilt a tényleges névvel, helyszínnel, órarenddel, fotókkal és a weboldal címével.
- [ ] **[Te]** A domain élesítése után állítsd be a Google Search Console-t, és kérd a főoldal indexelését.

## P2 – Kényelmi fejlesztések

- [ ] Készíts vendégoldalt, ahol a vendég áttekintheti a saját aktív foglalásait.
- [ ] Adj keresési és szűrési lehetőséget az órarendhez.
- [ ] Támogass több oktatót, termet és helyszínt.
- [ ] Készíts adminstatisztikákat és exportot a foglalásokról.
- [ ] Küldj automatikus emlékeztetőt az óra kezdete előtt.
