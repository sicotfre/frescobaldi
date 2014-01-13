# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2014 - 2014 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.

"""
The items a read music expression is constructed with.

Whitespace is left out, but comments are retained.

"""

from __future__ import unicode_literals

from fractions import Fraction

import node

import ly.duration
import ly.pitch
import ly.lex.lilypond


class Item(node.WeakNode):
    """Represents any item in the music of a document.
    
    This can be just a token, or an interpreted construct such as a note,
    rest or sequential or simultaneous construct , etc.
    
    Some Item instances just have one responsible token, but others have a
    list or tuple to tokens.
    
    An Item also has a pointer to the Document it originates from.
    
    """
    document = None
    tokens = ()
    token = None


class Token(Item):
    """Any token that is not otherwise recognized""" 


class Container(Item):
    """An item having a list of child items."""


class Duration(Item):
    """A duration"""
    base_scaling = None, None   # two Fractions
    

class Durable(Item):
    """An Item that has a Duration attribute."""
    duration = None
    
    def length(self):
        """Return the duration or None (no duration)."""
        if self.duration:
            base, scaling = self.duration.base_scaling
            return base * scaling

    def base_scaling(self):
        """Return the base and scaling fractions (if set, else None)."""
        if self.duration:
            return self.duration.base_scaling


class Chord(Durable, Container):
    pass


class Note(Durable):
    """A Note that has a ly.pitch.Pitch"""
    pitch = None


class Skip(Durable):
    pass


class Rest(Durable):
    pass


class Q(Durable):
    pass


class Music(Container):
    """Any music expression, to be inherited of."""
    def length(self):
        gen = (c.length() or 0 for c in self if isinstance(c, (Music, Durable)))
        return sum(gen)


class MusicList(Music):
    """A music expression, either << >> or { }."""
    simultaneous = False
    
    def length(self):
        gen = (c.length() or 0 for c in self if isinstance(c, (Music, Durable)))
        return max(gen) if self.simultaneous else sum(gen)


class Scaler(Music):
    """A music construct that scales the duration of its contents."""
    scaling = 1
    
    def length(self):
        return super(Scaler, self).length() * self.scaling


class Relative(Music):
    """A \\relative music expression. Has one or two children (Note, Music)."""
    pass


class Absolute(Music):
    """An \\absolute music expression. Has one child (normally Music)."""
    pass


class SchemeValue(Item):
    """The full list of tokens after a #."""
    def get_pair_ints(self):
        """Very basic way to get two integers specified as a pair."""
        result = [int(t) for t in self.tokens if t.isdigit()]
        if len(result) >= 2:
            return tuple(result[:2])


class StringValue(Item):
    """A double-quoted string."""
    
    def value(self):
        return ''.join(
            t[1:] if isinstance(t, ly.lex.Character) and t.startswith('\\') else t
            for t in self.tokens[:-1])


class Include(Item):
    """An \\include command (not changing the language)."""


class Language(Item):
    """A command (\\language or certain \\include commands) that changes the pitch language."""
    language = None


class Markup(Item):
    """A command starting markup (\markup, -lines and -list)."""


class MarkupCommand(Item):
    """A markup command, such as \italic etc."""


class MarkupScore(Item):
    """A \sore inside Markup."""


class MarkupList(Item):
    """The group of markup items inside { and }. NOTE: *not* a \markuplist."""


class MarkupWord(Item):
    """A MarkupWord token."""



class Reader(object):
    
    def __init__(self, source):
        """Initialize with a ly.document.Source.
        
        The language is set to "nederlands".
        
        """
        self.source = source
        self.language = "nederlands"
        self.in_chord = False
        self.prev_duration = Fraction(1, 4), 1
    
    def set_language(self, lang):
        """Changes the pitch name language to use.
        
        Called internally when \language or \include tokens are encoutered
        with a valid language name/file.
        
        Sets the language attribute to the language name.
        
        """
        if lang in ly.pitch.pitchInfo:
            self.language = lang
            return True

    def add_duration(self, item, token=None, source=None):
        """Add a duration attribute to the item.
        
        Returns the last token if there were more read from the source.
        
        """
        source = source or self.source
        d = item.duration = Duration()
        tokens = []
        if not token or isinstance(token, ly.lex.lilypond.Duration):
            if token:
                tokens.append(token)
            for token in source:
                if isinstance(token, ly.lex.lilypond.Duration):
                    tokens.append(token)
                elif not isinstance(token, ly.lex.Space):
                    break
            else:
                token = None
        if tokens:
            d.tokens = tuple(tokens)
            d.base_scaling = self.prev_duration = ly.duration.base_scaling(tokens)
        else:
            d.base_scaling = self.prev_duration
        return token
    
    def consume(self, source=None, last_token=None):
        """Yield the tokens until a parser is exit.
        
        If source is given, tokens are read from it, else from self.source.
        If last_token is given, it is called with the last token that is read.
        
        """
        source = source or self.source
        depth = self.source.state.depth()
        for t in source:
            yield t
            if self.source.state.depth() < depth:
                if last_token:
                    last_token(t)
                break

    def factory(self, cls, token, source=None):
        """Create Item instance for token, consuming(source) if given into item.tokens."""
        item = cls()
        item.token = token
        if source:
            item.tokens = tuple(self.consume(source))
        return item
    
    def read(self, source=None):
        """Yield Item instances reading from source."""
        
        source = source or self.source
        for t in source:
            while t:
                if isinstance(t, (ly.lex.Space, ly.lex.Comment)):
                    break
                elif isinstance(t, ly.lex.lilypond.MusicItem):
                    t, item = self.read_music_item(t, source)
                    if item:
                        yield item
                    else:
                        break   # t is an unknown note
                elif not self.in_chord and isinstance(t, ly.lex.lilypond.ChordStart):
                    self.in_chord = True
                    chord = self.factory(Chord, t)
                    def last(t): chord.tokens += (t,)
                    chord.extend(self.read(self.consume(source, last)))
                    self.in_chord = False
                    t = self.add_duration(chord, None, source)
                    yield chord
                elif isinstance(t, (ly.lex.lilypond.SequentialStart, ly.lex.lilypond.SimultaneousStart)):
                    item = self.factory(MusicList, t)
                    def last(t): item.tokens += (t,)
                    item.extend(self.read(self.consume(source, last)))
                    item.simultaneous = t == '<<'
                    yield item
                    break
                elif isinstance(t, ly.lex.lilypond.SchemeStart):
                    yield self.factory(SchemeValue, t, source)
                    break
                elif isinstance(t, ly.lex.StringStart):
                    yield self.factory(StringValue, t, source)
                    break
                elif isinstance(t, ly.lex.lilypond.Markup):
                    t, item = self.read_markup(t, source)
                    yield item
                elif isinstance(t, ly.lex.lilypond.Command):
                    yield self.read_command(t, source)
                    break
                elif isinstance(t, ly.lex.lilypond.Keyword):
                    yield self.read_keyword(t, source)
                    break
                elif isinstance(t, ly.lex.lilypond.UserCommand):
                    if t in ('\\simultaneous', '\\sequential'):
                        # these obscure commands are not even highlighted by ly.lex,
                        # but they exist in LilyPond...
                        # \simultaneous { ... } is like << ... >>
                        # but \sequential << ... >> just behaves like << ... >>
                        for i in self.read(source):
                            if isinstance(i, MusicList):
                                i.tokens = (i.token,) + i.tokens
                                i.token = t
                                i.simultaneous = i.simultaneous or t == '\\simultaneous'
                            yield i
                            break
                    break
                else:
                    break
                
    def read_music_item(self, t, source):
        """Read one music item (note, rest, s, \skip, or q) from t and source."""
        item = None
        in_pitch_command = isinstance(self.source.state.parser(), ly.lex.lilypond.ParsePitchCommand)
        if t.__class__ == ly.lex.lilypond.Note:
            r = ly.pitch.pitchReader(self.language)(t)
            if r:
                item = self.factory(Note, t)
                p = item.pitch = ly.pitch.Pitch(*r)
                t = None # prevent hang in this loop
                for t in source:
                    if isinstance(t, ly.lex.lilypond.Octave):
                        p.octave = ly.pitch.octaveToNum(t)
                        item.octave_token = t
                    elif isinstance(t, ly.lex.lilypond.Accidental):
                        item.accidental_token = p.accidental = t
                    elif isinstance(t, ly.lex.lilypond.OctaveCheck):
                        p.octavecheck = ly.pitch.octaveToNum(t)
                        item.octavecheck_token = t
                        break
                    elif not isinstance(t, ly.lex.Space):
                        break
        else:
            cls = {
                ly.lex.lilypond.Rest: Rest,
                ly.lex.lilypond.Skip: Skip,
                ly.lex.lilypond.Spacer: Skip,
                ly.lex.lilypond.Q: Q,
            }[t.__class__]
            item = self.factory(cls, t)
            t = None
        if item:
            if not self.in_chord and not in_pitch_command:
                t = self.add_duration(item, t, source)
        return t, item

    def read_command(self, t, source):
        """Read the rest of a command given in t from the source."""
        if t == '\\relative':
            item = self.factory(Relative, t)
            # get one pitch and exit on a non-comment
            pitch_found = False
            for i in self.read(source):
                item.append(i)
                if not pitch_found and isinstance(i, Note):
                    pitch_found = True
                    continue
                break
        elif t == '\\absolute':
            item = self.factory(Absolute, t)
            for i in self.read(source):
                item.append(i)
                break
        elif t in ('\\times', '\\tuplet', '\\scaleDurations'):
            item = self.factory(Scaler, t)
            item.scaling = 1
            if t == '\\scaleDurations':
                t = None
                for i in self.read(source):
                    item.append(i)
                    if isinstance(i, SchemeValue):
                        pair = i.get_pair_ints()
                        if pair:
                            item.scaling = Fraction(*pair)
                    break
            elif t == '\\tuplet':
                t = None
                for t in source:
                    if isinstance(t, ly.lex.lilypond.Fraction):
                        item.scaling = 1 / Fraction(t)
                    elif isinstance(t, ly.lex.lilypond.Duration):
                        t = self.add_duration(item, t, source)
                        break
                    elif not isinstance(t, ly.lex.Space):
                        break
            else: # t == '\\times'
                t = None
                for t in source:
                    if isinstance(t, ly.lex.lilypond.Fraction):
                        item.scaling = Fraction(t)
                        t = None
                        break
                    elif not isinstance(t, ly.lex.Space):
                        break
            # stick the last token back if needed
            for i in self.read(itertools.chain((t,), source) if t else source):
                item.append(i)
                break
        return item

    def read_keyword(self, t, source):
        """Read the rest of a keyword given in t from the source."""
        if t == '\\language':
            item = self.factory(Language, t)
            for name in self.read(source):
                item.append(name)
                if isinstance(name, StringValue):
                    value = item.language = name.value()
                    if value in ly.pitch.pitchInfo:
                        self.language = value
                break
        elif t == '\\include':
            item = None
            name = None
            for name in self.read(source):
                if isinstance(name, StringValue):
                    value = name.value()
                    if value.endswith('.ly') and value[:-3] in ly.pitch.pitchInfo:
                        item = self.factory(Language, t)
                        item.language = self.language = value[:-3]
                        item.append(name)
                break
            if not item:
                item = self.factory(Include, t)
                if name:
                    item.append(name)
        return item

    def read_markup(self, t, source):
        """Read LilyPond markup (recursively).
        
        Returns a two-tuple(token, item). Return t unmodified if item is None,
        else t can be the token that is read while a markup expression ended.
        
        """
        source = self.consume(source)
        if t in ('\\markup', '\\markuplist', '\\markuplines'):
            item = self.factory(Markup, t)
        elif isinstance(t, ly.lex.lilypond.MarkupScore):
            item = self.factory(MarkupScore, t)
            t = None
            for t in source:
                if isinstance(t, ly.lex.lilypond.OpenBracket):
                    item.tokens = (t,)
                    def last(t): item.tokens += (t,)
                    item.extend(self.read(self.consume(source, last)))
                    return None, item
            return t, item
        elif isinstance(t, ly.lex.lilypond.MarkupCommand):
            item = self.factory(MarkupCommand, t)
        elif isinstance(t, ly.lex.lilypond.OpenBracketMarkup):
            item = self.factory(MarkupList, t)
        elif isinstance(t, ly.lex.lilypond.MarkupWord):
            return None, self.factory(MarkupWord, t)
        elif isinstance(t, ly.lex.lilypond.SchemeStart):
            return None, self.factory(SchemeValue, t, source)
        elif isinstance(t, ly.lex.StringStart):
            return None, self.factory(StringValue, t, source)
        else:
            return t, None
        # add arguments
        t = None
        for t in source:
            t, i = self.read_markup(t, source)
            if i:
                item.append(i)
            elif isinstance(item, MarkupList) and isinstance(t, ly.lex.lilypond.CloseBracketMarkup):
                item.tokens = (t,)
        return t, item

