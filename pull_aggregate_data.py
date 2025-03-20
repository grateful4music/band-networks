import musicbrainzngs
import json
import time

# Set up MusicBrainz client with a descriptive User-Agent.
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
        result = musicbrainzngs.get_artist_by_id(band_id, includes=["artist-rels"])
        artist_data = result["artist"]
        band_name = artist_data.get("name", "Unknown")
        band = Band(band_id, band_name)

        # Process relationships to extract band members and (if available) supporting musicians.
        if "artist-relation-list" in artist_data:
            for rel in artist_data["artist-relation-list"]:
                rel_type = rel.get("type", "").lower()
                # MusicBrainz sometimes labels current/former members as "member of band" or "member"
                if rel_type in ["member of band", "member"]:
                    member = rel.get("artist")
                    if member:
                        band.add_member(member.get("name", "Unknown"), member.get("id", ""))
                # If there are supporting musicians (the relation type may vary), adjust as needed.
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
        result = musicbrainzngs.get_artist_by_id(member_id, includes=["artist-rels"])
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


def aggregate_data(seed_band_id):
    """
    Starting with a seed band, fetch the band’s details and then for each of its members
    and supporting musicians, fetch the bands they've been a part of (one level deep).
    
    Returns:
      dict: Aggregated data containing bands and connections for visualization.
    """
    # Dictionary to store Band instances keyed by MusicBrainz ID.
    bands_data = {}

    # Fetch seed band data.
    seed_band = fetch_band_data(seed_band_id)
    if seed_band is None:
        print("Failed to fetch seed band data.")
        return None
    bands_data[seed_band_id] = seed_band

    # Create a list of all persons (members and supporting musicians) to process.
    persons_to_process = []
    for person in seed_band.members:
        persons_to_process.append((person["id"], "member"))
    for person in seed_band.supporting_musicians:
        persons_to_process.append((person["id"], "supporting"))

    # For each person, fetch the bands they've been part of.
    for person_id, person_type in persons_to_process:
        print(f"Processing {person_type} with ID: {person_id}")
        person_bands = fetch_member_bands(person_id)
        # Respect the MusicBrainz rate limit.
        time.sleep(1.1)
        for b_id, b_name in person_bands:
            # Avoid duplicates.
            if b_id not in bands_data:
                print(f"  Fetching band: {b_name} (ID: {b_id})")
                new_band = fetch_band_data(b_id)
                if new_band:
                    bands_data[b_id] = new_band
                    time.sleep(1.1)

    # Create connections: for every pair of bands, if they share at least one musician (member or supporting),
    # record a connection with a weight equal to the number of shared musicians.
    connections = []
    band_ids = list(bands_data.keys())
    for i in range(len(band_ids)):
        for j in range(i + 1, len(band_ids)):
            band1 = bands_data[band_ids[i]]
            band2 = bands_data[band_ids[j]]
            # Collect musician IDs from both members and supporting musicians.
            musicians1 = {m["id"] for m in band1.members + band1.supporting_musicians}
            musicians2 = {m["id"] for m in band2.members + band2.supporting_musicians}
            shared = musicians1.intersection(musicians2)
            if shared:
                connections.append({
                    "source": band1.mbid,
                    "target": band2.mbid,
                    "weight": len(shared)
                })

    # Prepare the aggregated JSON structure.
    aggregated = {
        "bands": [band.to_dict() for band in bands_data.values()],
        "connections": connections
    }
    return aggregated


def main():
    # Replace with the MusicBrainz ID of your seed band.
    # seed_band_id = "5b11f4ce-a62d-471e-81fc-a69a8278c7da"  # Example: Nirvana's MBID
    seed_band_id = "a5585acd-9b65-49a7-a63b-3cc4ee18846e"  # Example: Mother Love Bone's MBID

    aggregated_data = aggregate_data(seed_band_id)
    if aggregated_data is None:
        print("Aggregation failed.")
        return

    # Write the aggregated data to a JSON file.
    output_filename = "bands_network.json"
    with open(output_filename, "w") as f:
        json.dump(aggregated_data, f, indent=2)

    print(f"Data aggregated and written to {output_filename}")


if __name__ == "__main__":
    main()
