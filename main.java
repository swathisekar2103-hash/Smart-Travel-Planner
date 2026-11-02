class animal
{
    void eat()
    {
        System.out.println("animals are eating");
    }
}
class dog extends animal
{
    void bark()
    {
        System.out.println("dogs are barking");
    }
}
class main
{
    public static void main(String args[])
    {
        dog ob=new dog();
        ob.eat();
        ob.bark();
    }
}