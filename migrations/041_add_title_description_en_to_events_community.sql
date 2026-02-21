-- Мультиязычность Community-событий: английский перевод (как в events)
-- Чтобы в обеих таблицах (events и events_community) данные были полными

ALTER TABLE events_community
ADD COLUMN IF NOT EXISTS title_en VARCHAR(255),
ADD COLUMN IF NOT EXISTS description_en TEXT;

COMMENT ON COLUMN events_community.title_en IS 'English translation of title for display when user language is en';
COMMENT ON COLUMN events_community.description_en IS 'English translation of description';

-- Архив: те же поля для полноты при переносе
ALTER TABLE events_community_archive
ADD COLUMN IF NOT EXISTS title_en VARCHAR(255),
ADD COLUMN IF NOT EXISTS description_en TEXT;

COMMENT ON COLUMN events_community_archive.title_en IS 'English translation of title (copied from events_community)';
COMMENT ON COLUMN events_community_archive.description_en IS 'English translation of description (copied from events_community)';
