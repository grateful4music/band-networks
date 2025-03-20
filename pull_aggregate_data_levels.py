import musicbrainzngs
import json
import time

# Set up the MusicBrainz client with a descriptive User-Agent.
musicbrainzngs.set_useragent("GrungeMappingProject", "0.1", "your-email@example.com")


class Band:
    """
    Represents a band with its MusicBrainz ID, name, members, and supporting musicians.
    """
    def __init__(self, mbid, name, members=None, supporting_musicians=None):
        self.mbid = mbid
        self.name = name
        self.members = members if members is not None else []  # List of dicts: {'name': ..., 'id': ...}
        self.supporting_musicians = supporting_musicians if supporting_musicians is not None else []

    def add_member(self, musician_name, musician_id):
        self.members.append({'name': musician_name, 'id': musician_id})

    def add_supporting_musician(self, musician_name, musician_id):
        self.supporting_musicians.append({'name': musician_name, 'id': musician_id})

    def to_dict(self):
        """Convert the Band instance to a dictionary for JSON export."""
        return {
            "id": self.mbid,
            "name": self.name,
            "members": self.members,
            "supporting_musicians": self.supporting_musicians
        }

    def __str__(self):
        return f"Band(name={self.name}, id={self.mbid})"

    def __repr__(self):
        return self.__str__()


def fetch_band_data(band_id):
    """
    Fetch a band's details from MusicBrainz (including relationships).

    Parameters:
      band_id (str): MusicBrainz ID of the band.

    Returns:
      Band: A Band instance populated with its members and supporting musicians.
    """
    try:
        # Include 'artist-rels' to get relationship data (members/supporting).
        result = musicbrainzngs.get_artist_by_id(band_id, includes=["artist-rels"], )
        artist_data = result["artist"]
        band_name = artist_data.get("name", "Unknown")
        band = Band(band_id, band_name)

        if "artist-relation-list" in artist_data:
            for rel in artist_data["artist-relation-list"]:
                rel_type = rel.get("type", "").lower()
                # Treat "member" or "member of band" as band members.
                if rel_type in ["member of band", "member"]:
                    member = rel.get("artist")
                    if member:
                        band.add_member(member.get("name", "Unknown"), member.get("id", ""))
                # For supporting musicians (if available) adjust the relation type as needed.
                elif rel_type in ["supporting musician"]:
                    musician = rel.get("artist")
                    if musician:
                        band.add_supporting_musician(musician.get("name", "Unknown"), musician.get("id", ""))
        return band
    except Exception as e:
        print(f"Error fetching band data for {band_id}: {e}")
        return None


def fetch_member_bands(member_id):
    """
    Given a musician's MusicBrainz ID, fetch all bands they've been a member of.

    Parameters:
      member_id (str): MusicBrainz ID of the musician.

    Returns:
      list of tuples: Each tuple is (band_id, band_name).
    """
    bands = []
    try:
        result = musicbrainzngs.get_artist_by_id(member_id, includes=["artist-rels"], )
        member_data = result["artist"]
        if "artist-relation-list" in member_data:
            for rel in member_data["artist-relation-list"]:
                rel_type = rel.get("type", "").lower()
                if rel_type in ["member of band", "member"]:
                    band_info = rel.get("artist")
                    if band_info:
                        bands.append((band_info.get("id"), band_info.get("name", "Unknown")))
    except Exception as e:
        print(f"Error fetching bands for member {member_id}: {e}")
    return bands


def aggregate_data(seed_band_id, max_depth=2):
    """
    Starting with a seed band, fetch the band's details and then (recursively up to max_depth)
    for each band member and supporting musician, fetch all the bands they've been a part of.

    Parameters:
      seed_band_id (str): MusicBrainz ID for the seed band.
      max_depth (int): Maximum depth for traversing bands.
                       Depth 0 is the seed band; depth 1 are bands of seed band persons, etc.

    Returns:
      dict: Aggregated data containing bands and connections for visualization.
    """
    bands_data = {}         # Key: band MBID, Value: Band instance
    processed_band_ids = set()  # To keep track of bands we've already fetched
    queue = [(seed_band_id, 0)]  # Each item is (band_id, current_depth)

    while queue:
        current_band_id, depth = queue.pop(0)
        if current_band_id in processed_band_ids:
            continue

        print(f"Fetching band (depth {depth}): {current_band_id}")
        band = fetch_band_data(current_band_id)
        if band:
            bands_data[current_band_id] = band
            processed_band_ids.add(current_band_id)

            # Only go deeper if we haven't reached max_depth.
            if depth < max_depth:
                # Combine members and supporting musicians.
                persons = band.members + band.supporting_musicians
                for person in persons:
                    person_id = person["id"]
                    person_bands = fetch_member_bands(person_id)
                    # Respect MusicBrainz rate limit.
                    time.sleep(1.1)
                    for b_id, b_name in person_bands:
                        if b_id not in processed_band_ids:
                            queue.append((b_id, depth + 1))
        else:
            print(f"Failed to fetch band: {current_band_id}")

    # Build connections: for every pair of bands, if they share at least one musician (member or supporting),
    # record a connection with a weight equal to the number of shared musicians.
    connections = []
    band_ids = list(bands_data.keys())
    for i in range(len(band_ids)):
        for j in range(i + 1, len(band_ids)):
            band1 = bands_data[band_ids[i]]
            band2 = bands_data[band_ids[j]]
            musicians1 = {m["id"] for m in band1.members + band1.supporting_musicians}
            musicians2 = {m["id"] for m in band2.members + band2.supporting_musicians}
            shared = musicians1.intersection(musicians2)
            if shared:
                connections.append({
                    "source": band1.mbid,
                    "target": band2.mbid,
                    "weight": len(shared)
                })

    aggregated = {
        "bands": [band.to_dict() for band in bands_data.values()],
        "connections": connections
    }
    return aggregated


def main():
    # Replace with the MusicBrainz ID of your seed band.
    seed_band_id = "a5585acd-9b65-49a7-a63b-3cc4ee18846e"
    aggregated_data = aggregate_data(seed_band_id, max_depth=2)
    if aggregated_data is None:
        print("Aggregation failed.")
        return

    # Write the aggregated data to a JSON file.
    output_filename = "bands_network_extended.json"
    with open(output_filename, "w") as f:
        json.dump(aggregated_data, f, indent=2)

    print(f"Data aggregated and written to {output_filename}")


if __name__ == "__main__":
    main()
