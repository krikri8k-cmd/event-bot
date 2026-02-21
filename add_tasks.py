#!/usr/bin/env python3
"""
DEPRECATED: Таблица tasks удалена. Квесты только из task_places. Скрипт не используется.
"""

import sys

if __name__ == "__main__":
    print("DEPRECATED: Таблица tasks удалена. Используйте task_places.", file=sys.stderr)
    sys.exit(0)

# Ниже старый код — не выполняется (таблица tasks удалена)
import os  # noqa: F401

import psycopg2  # noqa: F401
from dotenv import load_dotenv  # noqa: F401

load_dotenv("app.local.env")  # noqa: F405


def add_tasks():
    print("DEPRECATED: Таблица tasks удалена. Используйте task_places.", file=sys.stderr)
    sys.exit(0)
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tasks")
    count = cur.fetchone()[0]
    print(f"Current tasks count: {count}")

    if count == 0:
        # Добавляем задания для категории 'body'
        body_tasks = [
            (
                "body",
                "Yoga na pliazhe",
                "Poprobujte jogu na pliazhe utrom ili vecherom. Otlichnyj sposob nachat den s energiej!",
                "https://maps.google.com/maps?q=Kuta+Beach+Bali",
                1,
            ),
            (
                "body",
                "Probezhka po naberezhnoj",
                "Utrennyaya ili vechernyaya probezhka vdol okeana. Svezhiy vozduh i krasivye vidy!",
                "https://maps.google.com/maps?q=Sanur+Beach+Walk",
                2,
            ),
            (
                "body",
                "Utrennyaya rastyazhka",
                "Nachnite den s legkoy rastyazhkoy. Naydite tihoye mesto i potyanites 15-20 minut.",
                None,
                3,
            ),
            (
                "body",
                "Plavanie v okeane",
                "Poplavayte v okeane. Otlichnaya kardio-nagruzka i zakalivanie!",
                "https://maps.google.com/maps?q=Seminyak+Beach",
                4,
            ),
            (
                "body",
                "Velosipednaya progulka",
                "Prokatites na velosipede po okrestnostyam. Issledujte novye mesta!",
                "https://maps.google.com/maps?q=Ubud+Bike+Tour",
                5,
            ),
            (
                "body",
                "Trenirovka na svezhem vozduhe",
                "Sdelayte kompleks uprazhneniy na prirode. Otzhimaniya, prisedaniya, plank.",
                None,
                6,
            ),
            (
                "body",
                "Peshaya progulka po risovym terrasam",
                "Progulyaytes po risovym terrasam. Krasivye vidy i legkaya fizicheskaya aktivnost.",
                "https://maps.google.com/maps?q=Tegallalang+Rice+Terraces",
                7,
            ),
            (
                "body",
                "Serfing dlya nachinayuschih",
                "Poprobujte serfing! Nachnite s urokov na spokoynoy vode.",
                "https://maps.google.com/maps?q=Canggu+Beach+Surf",
                8,
            ),
            (
                "body",
                "Yoga v dzhunglyah",
                "Zanyatie jogoy v okruzhenii prirody. Naydite spokoynoye mesto sredi derevev.",
                "https://maps.google.com/maps?q=Ubud+Yoga+Center",
                9,
            ),
            (
                "body",
                "Plavanie v vodopade",
                "Poplavayte v prirodnom vodopade. Osvezhayusche i polezno dlya zdorovya!",
                "https://maps.google.com/maps?q=Tegenungan+Waterfall",
                10,
            ),
            (
                "body",
                "Utrennyaya zaryadka na pliazhe",
                "Sdelayte zaryadku na pliazhe na rassvete. Vstretite solnce s energiej!",
                "https://maps.google.com/maps?q=Jimbaran+Beach",
                11,
            ),
            (
                "body",
                "Peshiy pohod k vulkanu",
                "Sovershite pohod k vulkanu. Fizicheskaya nagruzka i neveroyatnye vidy!",
                "https://maps.google.com/maps?q=Mount+Batur",
                12,
            ),
            (
                "body",
                "Tancy na pliazhe",
                "Potancuyte na pliazhe pod zakat. Otlichnaya kardio-trenirovka!",
                "https://maps.google.com/maps?q=Legian+Beach",
                13,
            ),
            (
                "body",
                "Stretching v parke",
                "Potyanites v gorodskom parke. Naydite tihoye mesto i rasslabtes.",
                "https://maps.google.com/maps?q=Sanur+Beach+Park",
                14,
            ),
            (
                "body",
                "Plavanie s maskoy",
                "Poplavayte s maskoy i trubkoy. Issledujte podvodnyy mir!",
                "https://maps.google.com/maps?q=Nusa+Dua+Beach",
                15,
            ),
        ]

        # Добавляем задания для категории 'spirit'
        spirit_tasks = [
            (
                "spirit",
                "Meditaciya na rassvete",
                "Provedite 20 minut v meditacii na rassvete. Naydite tihoye mesto i sosredotochtes na dyhanii.",
                "https://maps.google.com/maps?q=Sanur+Beach+Sunrise",
                1,
            ),
            (
                "spirit",
                "Poseschenie hrama",
                "Posetite mestnyy hram. Poznakomtes s kulturoy i tradiciyami Bali.",
                "https://maps.google.com/maps?q=Besakih+Temple",
                2,
            ),
            (
                "spirit",
                "Progulka po svyaschennomu lesu",
                "Progulyaytes po svyaschennomu lesu obezyan. Pogruzites v atmosferu drevnosti.",
                "https://maps.google.com/maps?q=Sacred+Monkey+Forest",
                3,
            ),
            (
                "spirit",
                "Meditaciya u vodopada",
                "Pomeditiruyte u vodopada. Zvuki vody pomogut rasslabitsya i ochistit razum.",
                "https://maps.google.com/maps?q=Tibumana+Waterfall",
                4,
            ),
            (
                "spirit",
                "Ceremoniya ochischeniya",
                "Primite uchastie v ceremonii ochischeniya. Poznayte duhovnye praktiki Bali.",
                "https://maps.google.com/maps?q=Tirta+Empul+Temple",
                5,
            ),
            (
                "spirit",
                "Sozercanie zakata",
                "Provedite vremya v sozercanii zakata. Razmyshlyayte o proshedshem dne.",
                "https://maps.google.com/maps?q=Uluwatu+Temple+Sunset",
                6,
            ),
            (
                "spirit",
                "Progulka po risovym polyam",
                "Medlenno progulyaytes po risovym polyam. Nablyudayte za prirodoy i razmyshlyayte.",
                "https://maps.google.com/maps?q=Jatiluwih+Rice+Terraces",
                7,
            ),
            (
                "spirit",
                "Meditaciya v peschere",
                "Pomeditiruyte v peschere. Tishina i polumrak pomogut uglubitsya v sebya.",
                "https://maps.google.com/maps?q=Goa+Gajah+Cave",
                8,
            ),
            (
                "spirit",
                "Poseschenie duhovnogo centra",
                "Posetite duhovnyy centr ili ashram. Poznakomtes s praktikami samorazvitiya.",
                "https://maps.google.com/maps?q=Pyramids+of+Chi",
                9,
            ),
            (
                "spirit",
                "Progulka po botanicheskomu sadu",
                "Pogulyayte po botanicheskomu sadu. Nablyudayte za raznoobraziem rasteniy.",
                "https://maps.google.com/maps?q=Bali+Botanical+Garden",
                10,
            ),
            (
                "spirit",
                "Meditaciya na vershine holma",
                "Podnimites na holm i pomeditiruyte. Vid sverhu pomozhet obresti perspektivu.",
                "https://maps.google.com/maps?q=Campuhan+Ridge+Walk",
                11,
            ),
            (
                "spirit",
                "Poseschenie galerei iskusstva",
                "Posetite galereyu mestnogo iskusstva. Pogruzites v tvorcheskuyu atmosferu.",
                "https://maps.google.com/maps?q=ARMA+Museum",
                12,
            ),
            (
                "spirit",
                "Progulka po sadu speciy",
                "Pogulyayte po sadu speciy. Izuchite aromaty i ih vliyanie na nastroenie.",
                "https://maps.google.com/maps?q=Bali+Spice+Garden",
                13,
            ),
            (
                "spirit",
                "Meditaciya u ozera",
                "Pomeditiruyte u spokoynogo ozera. Otrazhenie v vode pomozhet nayti vnutrenniy pokoy.",
                "https://maps.google.com/maps?q=Lake+Batur",
                14,
            ),
            (
                "spirit",
                "Poseschenie centra remesel",
                "Posetite centr tradicionnyh remesel. Poznayte masterstvo i terpenie masterov.",
                "https://maps.google.com/maps?q=Ubud+Art+Market",
                15,
            ),
        ]

        all_tasks = body_tasks + spirit_tasks

        for task in all_tasks:
            cur.execute(
                """
                INSERT INTO tasks (category, title, description, location_url, order_index)
                VALUES (%s, %s, %s, %s, %s)
            """,
                task,
            )

        conn.commit()
        print(f"Added {len(all_tasks)} tasks: {len(body_tasks)} body + {len(spirit_tasks)} spirit")
    else:
        print("Tasks already exist, skipping insertion")

    cur.close()
    conn.close()


if __name__ == "__main__":
    add_tasks()
