import discord
import io

DISCORD_UPLOAD_LIMIT = 800000


def create_file_obj(
    input: str,
    encoding: str = "utf-8",
    name: str = "results",
    ext: str = "txt",
    spoiler: bool = False,
) -> discord.File:
    encoded = input.encode(encoding)
    if len(encoded) > DISCORD_UPLOAD_LIMIT:
        raise Exception("file is too large to upload")
    fp = io.BytesIO(encoded)
    filename = f"{name}.{ext}"
    return discord.File(fp=fp, filename=filename, spoiler=spoiler)
