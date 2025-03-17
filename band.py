class Band:
    """
    A class representing a band with its MusicBrainz ID, band name,
    list of band members, and list of supporting musicians.
    """

    def __init__(self, musicbrainz_id, name, members=None, supporting_musicians=None):
        """
        Initialize a Band instance.

        Parameters:
            musicbrainz_id (str): The MusicBrainz ID for the band.
            name (str): The band name.
            members (list): Optional. List of dicts representing band members.
                            Each dict should contain keys 'name' and 'id'.
            supporting_musicians (list): Optional. List of dicts representing supporting musicians.
                                         Each dict should contain keys 'name' and 'id'.
        """
        self.musicbrainz_id = musicbrainz_id
        self.name = name
        self.members = members if members is not None else []
        self.supporting_musicians = supporting_musicians if supporting_musicians is not None else []

    def add_member(self, member_name, member_id):
        """
        Add a band member.

        Parameters:
            member_name (str): Name of the band member.
            member_id (str): MusicBrainz ID of the band member.
        """
        self.members.append({'name': member_name, 'id': member_id})

    def add_supporting_musician(self, musician_name, musician_id):
        """
        Add a supporting musician.

        Parameters:
            musician_name (str): Name of the supporting musician.
            musician_id (str): MusicBrainz ID of the supporting musician.
        """
        self.supporting_musicians.append({'name': musician_name, 'id': musician_id})

    def __str__(self):
        return f"Band(name={self.name}, MusicBrainz ID={self.musicbrainz_id})"

    def __repr__(self):
        return self.__str__()


# Example usage:
if __name__ == "__main__":
    # Create a Band instance for Nirvana
    nirvana = Band("5b11f4ce-a62d-471e-81fc-a69a8278c7da", "Nirvana")
    
    # Add band members
    nirvana.add_member("Kurt Cobain", "a1b2c3d4")
    nirvana.add_member("Krist Novoselic", "e5f6g7h8")
    nirvana.add_member("Dave Grohl", "i9j0k1l2")
    
    # Add a supporting musician
    nirvana.add_supporting_musician("Pat Smear", "m3n4o5p6")
    
    # Print the band details
    print(nirvana)
    print("Band Members:", nirvana.members)
    print("Supporting Musicians:", nirvana.supporting_musicians)
